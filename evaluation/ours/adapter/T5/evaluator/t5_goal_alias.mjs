// T5-only reviewed single-placement aliases. Never sent to the Agent.
export const ALIAS_VERSION='t5-placement-alias-v2';
export function placementAlias(text){
 const match=String(text||'').match(/^\s*(?:please\s+)?move\s+(?:the\s+)?(cream cheese|cheese|wine bottle|bottle|bowl|plate)\s+(on|onto|in|into|inside|to)\s+(?:the\s+)?(top of (?:the )?cabinet|stove|plate|bowl|wine rack|rack)[.!\s]*$/i);
 if(!match)return null;
 let [,object,prep,destination]=match.map(s=>s.toLowerCase());
 object=({'cream cheese':'cheese',bottle:'wine bottle'})[object]||object;
 destination=destination.replace(/^top of (?:the )?cabinet$/,'top of the cabinet');
 if(destination==='wine rack')destination='rack';
 if(object==='cheese'&&destination==='bowl'&&['in','into','inside'].includes(prep))return 'put the cream cheese in the bowl';
 const surfaces=new Set(['bowl|stove','bowl|plate','bowl|top of the cabinet','wine bottle|rack','wine bottle|top of the cabinet']);
 if(['on','onto','to'].includes(prep)&&surfaces.has(object+'|'+destination))return 'put the '+object+' on '+(destination==='top of the cabinet'?'top of the cabinet':'the '+destination);
 return null;
}
