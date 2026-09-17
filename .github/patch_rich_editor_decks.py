from pathlib import Path

p=Path('index.html')
s=p.read_text()

# Styles: éditeurs riches compacts + gestion visuelle des decks.
css_marker='.color-line{display:grid;grid-template-columns:54px 1fr auto;gap:8px;align-items:center}'
css='''.inline-rich-editor{min-height:42px;padding:9px 10px;border:1px solid var(--line);border-radius:9px;background:#fff;font-weight:400;overflow-wrap:anywhere}.inline-rich-editor:empty:before{content:attr(data-placeholder);color:#9aa5b4;pointer-events:none}.inline-rich-editor:focus{outline:3px solid #7e9fe4;outline-offset:2px}.mini-richbar{gap:4px;margin-bottom:5px}.mini-richbar button{min-height:28px;padding:2px 8px;font-size:.76rem}.deck-editor{display:flex;flex-direction:column;gap:7px}.deck-editor-row{display:flex;gap:7px}.deck-editor-row input{flex:1;min-width:0}.deck-editor-row button{min-height:38px;padding:6px 10px}.deck-editor-chips{display:flex;gap:6px;flex-wrap:wrap;min-height:8px}.deck-chip{display:inline-flex;align-items:center;gap:5px;max-width:100%;padding:4px 7px;border:1px solid var(--line);border-radius:999px;background:#f5f7fa;font-size:.72rem;font-weight:550}.deck-chip span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.deck-chip button{width:19px;height:19px;min-height:19px;padding:0;border:0;border-radius:50%;background:#fff;font-size:.78rem;line-height:1}.deck-hint{color:var(--muted);font-size:.7rem;font-weight:400}.rich-field>span:first-child{font-size:.9rem;font-weight:650}
'''
if css_marker not in s: raise SystemExit('marqueur CSS introuvable')
s=s.replace(css_marker,css+css_marker,1)

# Titre et sous-titre deviennent des champs HTML inline enrichis.
old='''    <label>Nom complet<input id="name" required maxlength="240"></label>\n    <label>Sous-titre<input id="subtitle" maxlength="300"></label>'''
new='''    <div class="field rich-field"><span>Titre</span><div class="richbar mini-richbar"><button type="button" data-command="bold" data-rich-target="name"><b>B</b></button><button type="button" data-command="italic" data-rich-target="name"><i>I</i></button><button type="button" data-command="underline" data-rich-target="name"><u>U</u></button></div><div id="name" class="inline-rich-editor" contenteditable="true" role="textbox" aria-label="Titre enrichi" data-placeholder="Titre de l’événement"></div></div>\n    <div class="field rich-field"><span>Sous-titre</span><div class="richbar mini-richbar"><button type="button" data-command="bold" data-rich-target="subtitle"><b>B</b></button><button type="button" data-command="italic" data-rich-target="subtitle"><i>I</i></button><button type="button" data-command="underline" data-rich-target="subtitle"><u>U</u></button></div><div id="subtitle" class="inline-rich-editor" contenteditable="true" role="textbox" aria-label="Sous-titre enrichi" data-placeholder="Sous-titre court"></div></div>'''
if old not in s: raise SystemExit('champs titre/sous-titre introuvables')
s=s.replace(old,new,1)

# Ajout d'un éditeur de decks après les étiquettes.
old='''    <label>Étiquettes<input id="tags" placeholder="urbanisme, lois, culture"></label>'''
new=old+'''\n    <div class="full field"><span>Deck(s)</span><div class="deck-editor"><div id="deckEditorChips" class="deck-editor-chips"></div><div class="deck-editor-row"><input id="deckEditorInput" list="deckEditorOptions" placeholder="ICT::Thème::Chapitre" autocomplete="off"><datalist id="deckEditorOptions"></datalist><button id="deckEditorAdd" type="button">Ajouter</button></div><span class="deck-hint">Choisis un deck existant ou saisis un nouveau chemin avec <code>::</code>.</span></div></div>'''
if old not in s: raise SystemExit('champ étiquettes introuvable')
s=s.replace(old,new,1)

# Barre de description : cible explicite + souligné.
old='''<div class="richbar"><button type="button" data-command="bold"><b>Gras</b></button><button type="button" data-command="italic"><i>Italique</i></button><button type="button" data-command="insertUnorderedList">Liste</button><button type="button" id="link">Lien</button>'''
new='''<div class="richbar"><button type="button" data-command="bold" data-rich-target="description"><b>Gras</b></button><button type="button" data-command="italic" data-rich-target="description"><i>Italique</i></button><button type="button" data-command="underline" data-rich-target="description"><u>Souligné</u></button><button type="button" data-command="insertUnorderedList" data-rich-target="description">Liste</button><button type="button" id="link">Lien</button>'''
if old not in s: raise SystemExit('richbar description introuvable')
s=s.replace(old,new,1)

# Helpers de texte inline et decks.
marker='''function cleanInline(html){const t=document.createElement("template");t.innerHTML=String(html||"");const ok=new Set(["B","STRONG","I","EM","U","BR"]);function walk(p){for(const el of [...p.children]){if(!ok.has(el.tagName)){el.replaceWith(document.createTextNode(el.textContent));continue}for(const a of [...el.attributes])el.removeAttribute(a.name);walk(el)}}walk(t.content);return t.innerHTML}'''
addition=marker+'''\nfunction inlineText(html){const t=document.createElement("template");t.innerHTML=cleanInline(html);return(t.content.textContent||"").trim()}\nfunction allDeckPaths(){return[...new Set(rows.flatMap(e=>e.deck||[]).map(v=>String(v).trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"fr",{numeric:true,sensitivity:"base"}))}\nfunction renderDeckEditor(){const chips=$("deckEditorChips"),options=$("deckEditorOptions");if(!chips||!options)return;options.innerHTML=allDeckPaths().map(path=>'<option value="'+esc(path)+'"></option>').join("");chips.innerHTML="";editingExtras.deck.forEach((path,index)=>{const chip=document.createElement("span");chip.className="deck-chip";const text=document.createElement("span");text.textContent=path;const remove=document.createElement("button");remove.type="button";remove.textContent="×";remove.setAttribute("aria-label","Retirer le deck "+path);remove.onclick=()=>{editingExtras.deck.splice(index,1);renderDeckEditor()};chip.append(text,remove);chips.append(chip)})}\nfunction addDeckFromEditor(){const input=$("deckEditorInput"),path=String(input.value||"").trim();if(!path)return;if(path.length>300){$("error").textContent="Le nom du deck est trop long.";return}editingExtras.deck=uniqueStrings([...editingExtras.deck,path]);input.value="";renderDeckEditor()}'''
if marker not in s: raise SystemExit('cleanInline introuvable')
s=s.replace(marker,addition,1)

# Validation: conserver l'HTML inline au lieu de couper les balises au milieu.
old='''const x={...e,name:e.name.slice(0,240),subtitle:String(e.subtitle||"").slice(0,300),tags:e.tags.map(String),color:validColor(e.color),includeStart:e.includeStart!==false,includeEnd:e.includeEnd!==false,html:clean(e.html),deck:uniqueStrings(e.deck),image:uniqueStrings(e.image).map(safeImageSource).filter(Boolean)};bounds(x);return x'''
new='''const safeName=cleanInline(e.name),safeSubtitle=cleanInline(e.subtitle||"");if(!inlineText(safeName))throw Error("Le titre est obligatoire.");if(inlineText(safeName).length>240)throw Error("Le titre dépasse 240 caractères.");if(inlineText(safeSubtitle).length>300)throw Error("Le sous-titre dépasse 300 caractères.");const x={...e,name:safeName,subtitle:safeSubtitle,tags:e.tags.map(String),color:validColor(e.color),includeStart:e.includeStart!==false,includeEnd:e.includeEnd!==false,html:clean(e.html),deck:uniqueStrings(e.deck),image:uniqueStrings(e.image).map(safeImageSource).filter(Boolean)};bounds(x);return x'''
if old not in s: raise SystemExit('validation name/subtitle introuvable')
s=s.replace(old,new,1)

# Open editor: innerHTML + rendu decks.
old='''$("name").value=e?.name||"";$("subtitle").value=e?.subtitle||"";'''
new='''$("name").innerHTML=cleanInline(e?.name||"");$("subtitle").innerHTML=cleanInline(e?.subtitle||"");'''
if old not in s: raise SystemExit('openEditor title values introuvables')
s=s.replace(old,new,1)
old='''renderImageAttachments();setColor(e?.color||vividPalette.blue);'''
new='''renderImageAttachments();renderDeckEditor();$("deckEditorInput").value="";setColor(e?.color||vividPalette.blue);'''
if old not in s: raise SystemExit('openEditor attachments introuvable')
s=s.replace(old,new,1)

# Submit: lire le HTML enrichi plutôt que .value.
old='''name:$("name").value.trim(),subtitle:$("subtitle").value.trim(),'''
new='''name:cleanInline($("name").innerHTML),subtitle:cleanInline($("subtitle").innerHTML),'''
if old not in s: raise SystemExit('submit title values introuvables')
s=s.replace(old,new,1)

# Barres d'outils riches: cibler le champ indiqué plutôt que toujours la description.
old='''document.querySelectorAll("[data-command]").forEach(b=>{b.onmousedown=e=>e.preventDefault();b.onclick=()=>{$("description").focus();document.execCommand(b.dataset.command,false,null)}});'''
new='''document.querySelectorAll("[data-command]").forEach(b=>{b.onmousedown=e=>e.preventDefault();b.onclick=()=>{const target=$(b.dataset.richTarget||"description");if(!target)return;target.focus();document.execCommand(b.dataset.command,false,null)}});'''
if old not in s: raise SystemExit('handler data-command introuvable')
s=s.replace(old,new,1)

# Bouton Ajouter deck + Entrée dans le champ.
marker='''$("kind").onchange=updateKind;$("add").onclick=()=>openEditor();'''
new='''$("kind").onchange=updateKind;$("deckEditorAdd").onclick=addDeckFromEditor;$("deckEditorInput").onkeydown=e=>{if(e.key==="Enter"){e.preventDefault();addDeckFromEditor()}};$("add").onclick=()=>openEditor();'''
if marker not in s: raise SystemExit('handler kind/add introuvable')
s=s.replace(marker,new,1)

p.write_text(s)
