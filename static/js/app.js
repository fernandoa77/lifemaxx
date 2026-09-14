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

  document.querySelectorAll('[data-inline-edit]').forEach((field) => {
    const display = field.querySelector('.inline-display');
    const input = field.querySelector('.inline-control input, .inline-control textarea, .inline-control select');
    display?.addEventListener('click', () => {
      field.classList.add('editing');
      input?.focus();
      input?.select?.();
    });
    input?.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') field.classList.remove('editing');
      if (event.key === 'Enter' && input.tagName !== 'TEXTAREA') input.blur();
    });
    input?.addEventListener('blur', () => window.setTimeout(() => field.classList.remove('editing'), 250));
  });

  document.querySelectorAll('.photo-package-input').forEach((input) => {
    input.addEventListener('change', () => {
      const slot = input.closest('.photo-slot');
      const name = slot?.querySelector('[data-file-name]');
      slot?.classList.toggle('selected', Boolean(input.files?.length));
      if (name) name.textContent = input.files?.[0]?.name || 'Seleccionar';
    });
  });

  const gallery = document.getElementById('bodyPhotoGallery');
  document.querySelector('[data-open-gallery]')?.addEventListener('click', () => gallery?.showModal());
  document.querySelector('[data-close-gallery]')?.addEventListener('click', () => gallery?.close());
  gallery?.addEventListener('click', (event) => { if (event.target === gallery) gallery.close(); });

  const mealDialog = document.getElementById('mealDialog');
  const supplementDialog = document.getElementById('supplementDialog');
  document.querySelector('[data-open-meal]')?.addEventListener('click', () => mealDialog?.showModal());
  document.querySelector('[data-open-supplement]')?.addEventListener('click', () => supplementDialog?.showModal());
  if (mealDialog?.hasAttribute('data-open-on-load')) mealDialog.showModal();
  document.querySelectorAll('[data-close-dialog]').forEach((button) => button.addEventListener('click', () => button.closest('dialog')?.close()));
  document.querySelectorAll('.entry-dialog').forEach((dialog) => dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); }));

  const mealForm = document.querySelector('[data-meal-form]');
  const aiIntake = mealForm?.querySelector('[data-ai-intake]');
  const mealEditor = mealForm?.querySelector('[data-meal-editor]');
  const previewLabel = mealForm?.querySelector('[data-preview-label]');
  const aiGenerated = mealForm?.querySelector('[data-ai-generated]');
  document.querySelectorAll('[data-meal-mode]').forEach((button) => button.addEventListener('click', () => {
    const isAI = button.dataset.mealMode === 'ai';
    document.querySelectorAll('[data-meal-mode]').forEach((item) => item.classList.toggle('active', item === button));
    if (aiIntake) aiIntake.hidden = !isAI;
    if (mealEditor) mealEditor.hidden = isAI;
    if (previewLabel) previewLabel.hidden = true;
    if (aiGenerated && !isAI) aiGenerated.value = '0';
  }));

  const mealPhoto = mealForm?.querySelector('[data-meal-photo]');
  const mealFile = mealForm?.querySelector('[data-meal-file]');
  const showMealFile = () => {
    const file = mealPhoto?.files?.[0];
    if (mealFile) mealFile.textContent = file ? file.name : 'Seleccionar archivo · Ctrl + V';
    mealPhoto?.closest('[data-meal-image-drop]')?.classList.toggle('selected', Boolean(file));
  };
  mealPhoto?.addEventListener('change', showMealFile);
  mealDialog?.addEventListener('paste', (event) => {
    const image = [...(event.clipboardData?.items || [])].find((item) => item.type.startsWith('image/'))?.getAsFile();
    if (!image || !mealPhoto) return;
    const transfer = new DataTransfer();
    transfer.items.add(new File([image], image.name || `comida-${Date.now()}.png`, {type: image.type}));
    mealPhoto.files = transfer.files;
    showMealFile();
    event.preventDefault();
  });

  mealForm?.querySelector('[data-generate-meal]')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    const status = mealForm.querySelector('[data-ai-status]');
    const payload = new FormData(mealForm);
    payload.set('action', 'meal-ai-preview');
    button.disabled = true;
    if (status) status.textContent = 'Analizando…';
    try {
      const response = await fetch(location.href, {method: 'POST', body: payload, headers: {'X-Requested-With': 'XMLHttpRequest'}});
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || 'No se pudo analizar la comida.');
      const data = result.preview;
      ['calories', 'protein_g', 'carbs_g', 'fat_g', 'fiber_g', 'alcoholic_drink', 'beverage_volume_ml', 'alcohol_abv_percent', 'pure_alcohol_ml'].forEach((name) => {
        const input = mealForm.elements[name];
        if (input) input.value = data[name] ?? '';
      });
      mealForm.elements.description.value = data.notes || mealForm.elements.ai_description.value;
      mealForm.elements.foods_json.value = JSON.stringify(data.foods || []);
      aiGenerated.value = '1';
      mealEditor.hidden = false;
      previewLabel.hidden = false;
      if (status) status.textContent = `Vista previa generada · ${result.model}`;
    } catch (error) {
      if (status) status.textContent = error.message;
    } finally { button.disabled = false; }
  });

  window.setTimeout(() => document.querySelectorAll('.message').forEach(el => el.remove()), 4200);
})();
