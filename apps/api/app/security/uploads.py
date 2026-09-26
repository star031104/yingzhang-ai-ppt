"""Hard limits for multipart uploads, including requests without Content-Length."""

from fastapi import HTTPException, UploadFile


async def read_upload_limited(file: UploadFile, max_bytes: int, description: str) -> bytes:
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, f"{description}不能超过 {max_bytes // (1024 * 1024)} MB")
    return data
