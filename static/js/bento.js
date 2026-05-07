// Bento — small client-side helpers.
//
// `data-list-filter` on an <input> wires a case-insensitive prefix-anywhere
// filter against the closest sibling list of <li>s matching the selector.
// Used on Recents, Favorites, and the Mealie section of /saved-meals.

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('input[data-list-filter]').forEach((input) => {
    const targetSel = input.dataset.listFilter;
    const list = document.querySelector(targetSel);
    if (!list) return;

    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      list.querySelectorAll('li').forEach((li) => {
        if (!q) {
          li.style.display = '';
          return;
        }
        const text = li.innerText.toLowerCase();
        li.style.display = text.includes(q) ? '' : 'none';
      });
    });
  });
});
