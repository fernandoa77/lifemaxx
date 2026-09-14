(() => {
  const sidebar = document.getElementById('sidebar');
  document.getElementById('menuToggle')?.addEventListener('click', () => sidebar?.classList.toggle('open'));
  document.addEventListener('click', (event) => {
    if (window.innerWidth <= 760 && sidebar?.classList.contains('open') && !sidebar.contains(event.target) && event.target.id !== 'menuToggle') sidebar.classList.remove('open');
  });

  const indicator = document.querySelector('[data-save-indicator]');
  const setStatus = (label, kind = '') => {
    if (!indicator) return;
    indicator.className = `save-indicator ${kind}`;
    indicator.innerHTML = `<i></i> ${label}`;
  };

  document.querySelectorAll('form[data-autosave="true"]').forEach((form) => {
    let timer;
    let saving = false;
    const save = async () => {
      if (saving) return;
      saving = true;
      setStatus('Guardando…', 'saving');
      try {
        const response = await fetch(form.action || location.href, {
          method: 'POST', body: new FormData(form), headers: {'X-Requested-With': 'XMLHttpRequest'}
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error('No se pudo guardar');
        setStatus('Guardado', 'saved');
        window.setTimeout(() => location.reload(), 450);
      } catch (error) {
        setStatus('Error · reintenta', 'error');
      } finally { saving = false; }
    };
    form.querySelectorAll('input:not([type="hidden"]), select, textarea').forEach((field) => {
      field.addEventListener('change', () => { clearTimeout(timer); timer = setTimeout(save, 150); });
      if (field.tagName === 'TEXTAREA' || field.type === 'text' || field.type === 'number') {
        field.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(save, 900); });
      }
    });
    form.addEventListener('submit', (event) => { event.preventDefault(); clearTimeout(timer); save(); });
  });

  window.setTimeout(() => document.querySelectorAll('.message').forEach(el => el.remove()), 4200);
})();
