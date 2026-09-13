import fs from 'node:fs/promises'
import {createHash} from 'node:crypto'
import {isDeepStrictEqual} from 'node:util'

const fields=['id','position','role','message','content','sourceRefs','assetBindings','designSystem','layoutPlan']
export function renderInput(spec){
 const value=Object.fromEntries(fields.map(key=>[key,spec[key]??null]))
 value.visualIntent=Object.fromEntries(Object.entries(spec.visualIntent??{}).filter(([key])=>!['selectedVariant','variantSelectionSource','criticIssues'].includes(key)))
 return structuredClone(value)
}
export async function assetDigests(spec){
 const paths=[...(spec.assetBindings??[]).map(asset=>asset.path),spec.designSystem?.brand?.logoPath].filter(Boolean)
 const result={}
 for(const file of new Set(paths)){
  try{result[file]=createHash('sha256').update(await fs.readFile(file)).digest('hex')}catch{result[file]=null}
 }
 return result
}
export async function renderStamp(spec){return {version:2,input:renderInput(spec),assets:await assetDigests(spec)}}
export async function matchesRenderStamp(stamp,spec){
 return stamp?.version===2&&isDeepStrictEqual(stamp.input,renderInput(spec))&&isDeepStrictEqual(stamp.assets,await assetDigests(spec))
}
