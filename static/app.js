function toggle(id){document.getElementById(id)?.classList.toggle('hidden')}
function brl(v){return new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}).format(v||0)}
function updateCart(){let boxes=[...document.querySelectorAll('.sale-item:checked')];let subtotal=boxes.reduce((s,b)=>s+Number(b.dataset.price),0);let d=Number(document.getElementById('discount')?.value||0);d=Math.max(0,Math.min(d,subtotal));document.getElementById('subtotal').textContent=brl(subtotal);document.getElementById('total').textContent=brl(subtotal-d);document.getElementById('item_ids').value=boxes.map(b=>b.value).join(',')}
function prepareSale(){updateCart();if(!document.getElementById('item_ids').value){alert('Selecione pelo menos uma peça.');return false}return true}
function filterItems(){let q=(document.getElementById('filter').value||'').toLowerCase();document.querySelectorAll('#products .product').forEach(el=>{el.style.display=el.dataset.name.includes(q)?'flex':'none'})}
