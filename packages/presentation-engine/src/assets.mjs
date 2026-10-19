import fs from 'node:fs/promises'
import path from 'node:path'
import {pathToFileURL} from 'node:url'

// Inline bound images and the brand logo so the HTML candidate is self-contained.
export async function hydrateAssets(spec){
 const clone=structuredClone(spec),assets=clone.assetBindings??[]
 clone.assetLoadErrors=[]
 for(const asset of assets){
  if(!asset.path||asset.dataUri)continue
  if(['licensed-video','licensed-audio'].includes(asset.type)){asset.mediaUri=pathToFileURL(asset.path).href;continue}
  try{
   const data=await fs.readFile(asset.path),ext=path.extname(asset.path).toLowerCase()
   const mime=ext==='.svg'?'image/svg+xml':ext==='.jpg'||ext==='.jpeg'?'image/jpeg':ext==='.webp'?'image/webp':'image/png'
   asset.dataUri=`data:${mime};base64,${data.toString('base64')}`
  }catch{clone.assetLoadErrors.push({code:'missing-asset',severity:'error',message:'绑定的图片文件无法读取',assetId:asset.id??null})}
 }
 const logoPath=clone.designSystem?.brand?.logoPath
 if(logoPath){
  try{
   const data=await fs.readFile(logoPath),ext=path.extname(logoPath).toLowerCase()
   const mime=ext==='.svg'?'image/svg+xml':ext==='.jpg'||ext==='.jpeg'?'image/jpeg':'image/png'
   clone.designSystem.brand.logoDataUri=`data:${mime};base64,${data.toString('base64')}`
  }catch{clone.assetLoadErrors.push({code:'missing-asset',severity:'error',message:'品牌标识文件无法读取'})}
 }
 return clone
}
