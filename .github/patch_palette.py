from pathlib import Path

p=Path('index.html')
s=p.read_text()

css_marker='@media(max-width:720px)'
css='''.palette-tool{position:relative}.palette-panel{position:absolute;right:0;top:40px;z-index:38;width:min(340px,calc(100vw - 24px));padding:12px;background:#fff;border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow)}.palette-head{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:.78rem}.palette-head label{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:.72rem}.palette-head select{min-height:30px;padding:3px 24px 3px 7px}.palette-colors{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:11px 0}.palette-colors input[type="color"]{width:100%;height:42px;padding:2px;border-radius:8px;cursor:pointer}.palette-actions{display:flex;gap:6px;flex-wrap:wrap}.palette-actions button{min-height:32px;padding:5px 9px;font-size:.74rem}.palette-note{margin:8px 0 0;color:var(--muted);font-size:.67rem;line-height:1.25}\n'''
if css_marker not in s: raise SystemExit('marqueur CSS introuvable')
s=s.replace(css_marker,css+css_marker,1)

old_header='<div class="header-actions"><button id="randomEvent" type="button" aria-label="Tirer un événement au hasard" title="Tirer un événement au hasard">🎲</button><div class="file-menu">'
new_header='<div class="header-actions"><button id="randomEvent" type="button" aria-label="Tirer un événement au hasard" title="Tirer un événement au hasard">🎲</button><div class="palette-tool"><button id="paletteButton" type="button" aria-label="Tester une palette temporaire" title="Tester une palette temporaire" aria-expanded="false">🎨</button><div id="palettePanel" class="palette-panel" hidden><div class="palette-head"><strong>Palette temporaire</strong><label><select id="paletteCount" aria-label="Nombre de couleurs"><option value="6">6</option><option value="7">7</option><option value="8" selected>8</option></select> couleurs</label></div><div id="paletteColors" class="palette-colors"></div><div class="palette-actions"><button id="harmoniousPalette" type="button">🎲 Harmonie</button><button id="applyPalette" type="button" class="primary">Appliquer</button><button id="resetPalette" type="button">Original</button></div><p class="palette-note">Essai visuel uniquement · rien n’est enregistré.</p></div></div><div class="file-menu">'
if old_header not in s: raise SystemExit('header palette introuvable')
s=s.replace(old_header,new_header,1)

old_palette='const vividPalette={green:"#B2F23A",blue:"#21BCFF",orange:"#FE9A37",red:"#FF2056",pink:"#ED6AFF",violet:"#7C86FF",brown:"#FFDF20",turquoise:"#46ECD5"};'
new_palette=old_palette+'''
const temporaryPaletteDefaults=[vividPalette.green,vividPalette.blue,vividPalette.pink,vividPalette.orange,vividPalette.brown,vividPalette.red,vividPalette.violet,vividPalette.turquoise];
let temporaryPalette=[...temporaryPaletteDefaults],temporaryPaletteCount=8,temporaryPaletteActive=false;
const temporaryPaletteAssignments=new Map;
function paletteRandomUnit(){const a=new Uint32Array(1);crypto.getRandomValues(a);return a[0]/4294967295}
function paletteRandomIndex(n){return Math.floor(paletteRandomUnit()*Math.max(1,n))%Math.max(1,n)}
function temporaryEventColor(e){if(!temporaryPaletteActive)return e.color;if(!temporaryPaletteAssignments.has(e.id))temporaryPaletteAssignments.set(e.id,paletteRandomIndex(temporaryPaletteCount));return temporaryPalette[temporaryPaletteAssignments.get(e.id)%temporaryPaletteCount]||e.color}
function renderTemporaryPaletteInputs(){const box=$("paletteColors");if(!box)return;box.innerHTML="";temporaryPalette.slice(0,temporaryPaletteCount).forEach((c,i)=>{const input=document.createElement("input");input.type="color";input.value=c;input.setAttribute("aria-label","Couleur "+(i+1));input.oninput=()=>{temporaryPalette[i]=validColor(input.value);if(temporaryPaletteActive)render()};box.append(input)})}
function applyTemporaryPalette(message=true){temporaryPaletteActive=true;temporaryPaletteAssignments.clear();render();if(message)notice("Palette temporaire appliquée · elle disparaîtra au prochain rechargement.")}
function resetTemporaryPalette(){temporaryPaletteActive=false;temporaryPaletteAssignments.clear();render();notice("Couleurs d’origine restaurées.")}
function harmoniousTemporaryPalette(){const n=temporaryPaletteCount,base=paletteRandomUnit()*360,mode=paletteRandomIndex(4),hues=[];for(let i=0;i<n;i++){let h;if(mode===0)h=base+(i-(n-1)/2)*(100/Math.max(1,n-1));else if(mode===1){const offsets=[0,22,44,180,202,224,90,270];h=base+offsets[i%offsets.length]}else if(mode===2)h=base+(i%3)*120+Math.floor(i/3)*14;else h=base+(i%4)*90+Math.floor(i/4)*16;h=(h%360+360)%360;const sat=66+paletteRandomUnit()*20,light=48+paletteRandomUnit()*14;hues.push(hex(hsl(h,sat,light)))}temporaryPalette=[...hues,...temporaryPalette.slice(n)];renderTemporaryPaletteInputs();applyTemporaryPalette(false);notice("Nouvelle harmonie temporaire appliquée.")}
function closeTemporaryPalettePanel(){const panel=$("palettePanel"),button=$("paletteButton");if(panel)panel.hidden=true;if(button)button.setAttribute("aria-expanded","false")}
'''
if old_palette not in s: raise SystemExit('vividPalette introuvable')
s=s.replace(old_palette,new_palette,1)

old_card='button.style.setProperty("--event-color",e.color);'
if old_card not in s: raise SystemExit('couleur de carte introuvable')
s=s.replace(old_card,'button.style.setProperty("--event-color",temporaryEventColor(e));',1)

old_handler='$("randomEvent").onclick=e=>{e.stopPropagation();showRandomEvent()};$("fileMenuButton").onclick=e=>{'
new_handler='$("randomEvent").onclick=e=>{e.stopPropagation();showRandomEvent()};renderTemporaryPaletteInputs();$("paletteButton").onclick=e=>{e.stopPropagation();closeFileMenu();closeDeckMenu();const panel=$("palettePanel"),open=panel.hidden;panel.hidden=!open;$("paletteButton").setAttribute("aria-expanded",String(open));if(open)renderTemporaryPaletteInputs()};$("palettePanel").onclick=e=>e.stopPropagation();$("paletteCount").onchange=()=>{temporaryPaletteCount=Number($("paletteCount").value);temporaryPaletteAssignments.clear();renderTemporaryPaletteInputs();if(temporaryPaletteActive)render()};$("applyPalette").onclick=()=>applyTemporaryPalette();$("harmoniousPalette").onclick=harmoniousTemporaryPalette;$("resetPalette").onclick=resetTemporaryPalette;$("fileMenuButton").onclick=e=>{'
if old_handler not in s: raise SystemExit('handler random introuvable')
s=s.replace(old_handler,new_handler,1)

old_escape='document.addEventListener("keydown",e=>{if(e.key==="Escape"){closeFileMenu();closeDeckMenu();'
new_escape='document.addEventListener("keydown",e=>{if(e.key==="Escape"){closeTemporaryPalettePanel();closeFileMenu();closeDeckMenu();'
if old_escape not in s: raise SystemExit('escape introuvable')
s=s.replace(old_escape,new_escape,1)

old_doc='document.addEventListener("click",e=>{if(!$("fileMenu").hidden)closeFileMenu();'
new_doc='document.addEventListener("click",e=>{if(!$("palettePanel").hidden&&!e.target.closest(".palette-tool"))closeTemporaryPalettePanel();if(!$("fileMenu").hidden)closeFileMenu();'
if old_doc not in s: raise SystemExit('document click introuvable')
s=s.replace(old_doc,new_doc,1)

p.write_text(s)
