export const sceneNodeTypes=['text','shape','image','svg','group','chart','diagram','table','video','raster'];export function validateScene(scene){if(!scene||!Number.isFinite(scene.width)||!Number.isFinite(scene.height)||!Array.isArray(scene.nodes))throw new Error('Invalid Scene IR');for(const node of scene.nodes){if(!sceneNodeTypes.includes(node.type)||!node.bbox)throw new Error(`Invalid scene node ${node.id??'unknown'}`)}if(scene.exportLayer!==undefined)validateExportLayer(scene.exportLayer);return scene}

// Export layer (scene-export-v1): painted primitives in CSS px of a 1280×720
// slide, sorted in paint order. It drives the scene-based PPTX compiler.
export const exportItemKinds=['box','text','image','table','chart','vector','svg','media']
export function validateExportLayer(layer){
 if(!layer||layer.version!=='scene-export-v1'||!Array.isArray(layer.items))throw new Error('Invalid scene export layer')
 for(const [index,item] of layer.items.entries()){
  if(!exportItemKinds.includes(item.kind))throw new Error(`Invalid export item kind at ${index}`)
  if(!['x','y','w','h','order','z'].every(key=>Number.isFinite(item[key])))throw new Error(`Invalid export item geometry at ${index}`)
  if(item.kind==='text'&&(!Array.isArray(item.runs)||!item.runs.length))throw new Error(`Text export item ${index} has no runs`)
  if(item.kind==='table'&&!Array.isArray(item.rows))throw new Error(`Table export item ${index} has no rows`)
  if(item.kind==='chart'&&item.model?.version!=='chart-v1')throw new Error(`Chart export item ${index} has no chart model`)
  if(item.kind==='vector'&&!Array.isArray(item.shapes))throw new Error(`Vector export item ${index} has no shapes`)
 }
 return layer
}
