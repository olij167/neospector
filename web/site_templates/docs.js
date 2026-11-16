(function(){'use strict';
const d=JSON.parse(document.getElementById('docs-data').textContent);
const nav=document.getElementById('docs-nav');const target=document.getElementById('docs-sections');
document.getElementById('docs-title').textContent=d.title||'Neospector guide';
document.getElementById('docs-intro').textContent=d.introduction||'';
for(const section of d.sections||[]){
 if(!section||!/^[a-z][a-z0-9-]{0,40}$/.test(section.id))continue;
 const link=document.createElement('a');link.href='#'+section.id;link.textContent=section.title||section.id;nav.append(link);
 const article=document.createElement('section');article.id=section.id;
 const h=document.createElement('h2');h.textContent=section.title;article.append(h);
 const paras=String(section.body||'').split(/\n\s*\n/);
 for(const paragraph of paras){if(!paragraph.trim())continue;const p=document.createElement('p');p.style.whiteSpace='pre-line';p.textContent=paragraph;article.append(p);}
 for(const entry of section.media||[]){if(!entry||!/^\/downloads\/neospector\/media\/[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(entry.src||''))continue;
  const fig=document.createElement('figure');const el=document.createElement(entry.type==='video'?'video':'img');el.src=entry.src;
  if(entry.type==='video'){el.controls=true;el.preload='metadata';}else{el.alt=entry.alt||'';el.loading='lazy';}
  fig.append(el);if(entry.caption){const c=document.createElement('figcaption');c.textContent=entry.caption;fig.append(c);}article.append(fig);
 }
 target.append(article);
}
})();
