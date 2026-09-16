from pathlib import Path

p = Path('index.html')
s = p.read_text()

# Tableau : le point de couleur suit aussi la palette temporaire.
s = s.replace("'<span style=\"color:'+e.color+'\">●</span> '", "'<span style=\"color:'+temporaryEventColor(e)+'\">●</span> '")

# Fiche détail : bordure et date suivent la palette temporaire.
s = s.replace('d.style.setProperty("--event-color",e.color);', 'd.style.setProperty("--event-color",temporaryEventColor(e));')

# Tout le rendu de la frise (traits, points, périodes, hachures, dates) utilise
# la couleur visuelle temporaire sans toucher à la donnée e.color.
start = s.find('function draw(events){')
end = s.find('function renderImageAttachments()', start)
if start < 0 or end < 0:
    raise SystemExit('fonction draw introuvable')
block = s[start:end]
block = block.replace('it.e.color', 'temporaryEventColor(it.e)')
block = block.replace('e.color', 'temporaryEventColor(e)')
s = s[:start] + block + s[end:]

p.write_text(s)
