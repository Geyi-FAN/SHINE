import {lstatSync,readlinkSync,symlinkSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
export function ensureSymlink(target,link){
 let st;try{st=lstatSync(link)}catch(e){if(e.code!=='ENOENT')throw e}
 if(!st){symlinkSync(target,link);return 'created'}
 if(!st.isSymbolicLink()||resolve(dirname(link),readlinkSync(link))!==resolve(target))throw new Error('recording_alias_conflict:'+link);
 return 'existing_same_target';
}
