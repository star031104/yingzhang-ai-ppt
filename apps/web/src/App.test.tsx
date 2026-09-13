import '@testing-library/jest-dom/vitest'
import {render,screen} from '@testing-library/react'
import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {expect,test,vi} from 'vitest'
import {App} from './App'
import {getProjects} from './api'

vi.stubGlobal('fetch',vi.fn(()=>Promise.resolve({ok:true,json:()=>Promise.resolve([])})))

test('呈现中文端到端创建流程',()=>{
  render(<QueryClientProvider client={new QueryClient()}><App session={{authenticated:true,name:'本机管理员',role:'admin',publicMode:false}} onLogout={()=>{}}/></QueryClientProvider>)
  expect(screen.getByText('开始一场有章法的演示')).toBeInTheDocument()
  expect(screen.getByText('开始智能生成 →')).toBeInTheDocument()
  expect(screen.getByText('模型配置')).toBeInTheDocument()
  expect(screen.getByText('技能库')).toBeInTheDocument()
  expect(screen.getByText('本地工作区')).toBeInTheDocument()
  expect(screen.getByText('我的助手')).toBeInTheDocument()
  expect(screen.queryByText('退出登录')).not.toBeInTheDocument()
  expect(screen.getByText('参考材料')).toBeInTheDocument()
  const materials = screen.getByLabelText(/参考材料/) as HTMLInputElement
  expect(materials.multiple).toBe(true)
  expect(materials.name).toBe('sources')
  expect(screen.getByText('内置专业流程')).toBeInTheDocument()
  expect(screen.getByText('高管决策简报')).toBeInTheDocument()
})

test('Cloudflare 超时不会把 HTML 错误页展示给用户',async()=>{
  vi.stubGlobal('fetch',vi.fn(()=>Promise.resolve({
    ok:false,
    status:524,
    headers:new Headers({'content-type':'text/html'}),
    text:()=>Promise.resolve('<!DOCTYPE html><title>524: A timeout occurred</title>'),
  })))
  await expect(getProjects()).rejects.toThrow('公网连接等待超时')
})
