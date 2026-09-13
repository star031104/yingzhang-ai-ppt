"""Real desktop/office rendering. Missing software never counts as verification."""
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from app.config import settings


def registered_office(progid):
    if os.name != "nt":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid + r"\CLSID") as key:
            return bool(winreg.QueryValueEx(key, "")[0])
    except OSError:
        return False


def capabilities():
    executable = settings.office_executable or shutil.which("libreoffice") or shutil.which("soffice")
    if not executable and os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "LibreOffice/program/soffice.exe"
        executable = str(candidate) if candidate.is_file() else None
    return {"libreoffice": executable, "powerpoint-windows": registered_office("PowerPoint.Application"), "wps": registered_office("KWPP.Application"),
            "powerpoint-macos": False, "localOnly": settings.local_only_mode,
            "note": "已检查本机自动化接口；文件能否正常打开仍需通过实际渲染验证"}


def render_office(source: Path, output: Path, software="libreoffice"):
    import pymupdf
    source = source.resolve()
    output.mkdir(parents=True, exist_ok=True)
    output = output.resolve()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    pdf = output / (source.stem + ".pdf")
    pdf.unlink(missing_ok=True)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        if software == "libreoffice":
            executable = capabilities()["libreoffice"]
            if not executable:
                return {"status": "unavailable", "software": software, "fileHash": source_hash, "message": "本机未找到 LibreOffice"}
            profile = (output / "office-profile").as_uri()
            result = subprocess.run([executable, f"-env:UserInstallation={profile}", "--headless", "--convert-to", "pdf", "--outdir", str(output), str(source)],
                                    capture_output=True, timeout=180, creationflags=flags)
        elif software in {"powerpoint-windows", "wps"} and os.name == "nt":
            progid = "PowerPoint.Application" if software == "powerpoint-windows" else "KWPP.Application"
            if not registered_office(progid):
                label = "WPS" if software == "wps" else "PowerPoint"
                return {"status": "unavailable", "software": software, "fileHash": source_hash,
                        "message": f"本机没有注册 {label} 的自动化接口，无法自动生成验收预览。可选择其他已安装软件，或在 {label} 中手动导出 PDF 后上传验收。"}
            # Paths are environment values, never interpolated into executable code.
            script = output / "render-office.ps1"
            script.write_text("""$ErrorActionPreference = 'Stop'
$app = $null
$deck = $null
$alreadyRunning = @(Get-Process -Name $env:YZ_OFFICE_PROCESS -ErrorAction SilentlyContinue).Count -gt 0
$previousSecurity = $null
try {
  $app = New-Object -ComObject $env:YZ_OFFICE_PROGID
  $previousSecurity = $app.AutomationSecurity
  $app.AutomationSecurity = 3
  $deck = $app.Presentations.Open($env:YZ_OFFICE_INPUT, $true, $false, $false)
  $deck.SaveAs($env:YZ_OFFICE_OUTPUT, 32)
} finally {
  if ($deck) { $deck.Close() }
  if ($app) {
    if ($null -ne $previousSecurity) { $app.AutomationSecurity = $previousSecurity }
    if (-not $alreadyRunning) { $app.Quit() }
  }
}
""", encoding="utf-8")
            env = {**os.environ, "YZ_OFFICE_INPUT": str(source), "YZ_OFFICE_OUTPUT": str(pdf),
                   "YZ_OFFICE_PROGID": "PowerPoint.Application" if software == "powerpoint-windows" else "KWPP.Application",
                   "YZ_OFFICE_PROCESS": "POWERPNT" if software == "powerpoint-windows" else "wpp"}
            result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-File", str(script)],
                                    env=env, capture_output=True, timeout=180, creationflags=flags)
        else:
            return {"status": "unavailable", "software": software, "fileHash": source_hash, "message": "本机不支持该桌面软件的自动化，请使用手工验收"}
        if result.returncode or not pdf.is_file():
            return {"status": "failed", "software": software, "fileHash": source_hash,
                    "message": "目标软件未成功生成 PDF，请检查安装与文档兼容性"}
        pages = []
        with pymupdf.open(pdf) as document:
            for index, page in enumerate(document):
                target = output / f"page-{index+1}.png"
                page.get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3)).save(target)
                pages.append({"page": index+1, "image": target.name, "textLength": len(page.get_text()),
                              "text": page.get_text()})
        return {"status": "rendered-needs-review", "software": software, "fileHash": source_hash,
                "pageCount": len(pages), "pages": pages, "pdf": pdf.name}
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "failed", "software": software, "fileHash": source_hash, "message": "目标软件无法启动或渲染超时"}
