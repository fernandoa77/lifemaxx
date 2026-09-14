(() => {
  const sidebar = document.getElementById('sidebar');
  document.getElementById('menuToggle')?.addEventListener('click', () => sidebar?.classList.toggle('open'));
  document.addEventListener('click', (event) => {
    if (sidebar?.classList.contains('open') && !sidebar.contains(event.target) && event.target.id !== 'menuToggle') sidebar.classList.remove('open');
  });

  let openCustomSelect = null;
  const closeCustomSelect = () => {
    if (!openCustomSelect) return;
    openCustomSelect.classList.remove('open');
    openCustomSelect.querySelector('.custom-select-trigger')?.setAttribute('aria-expanded', 'false');
    openCustomSelect = null;
  };
  document.querySelectorAll('select').forEach((select, selectIndex) => {
    if (select.dataset.nativeSelect === 'true') return;
    const wrapper = document.createElement('div');
    const trigger = document.createElement('button');
    const menu = document.createElement('div');
    const menuId = `custom-select-${selectIndex}`;
    wrapper.className = `custom-select${select.disabled ? ' disabled' : ''}`;
    trigger.type = 'button';
    trigger.className = 'custom-select-trigger';
    trigger.disabled = select.disabled;
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-controls', menuId);
    menu.className = 'custom-select-menu';
    menu.id = menuId;
    menu.setAttribute('role', 'listbox');
    menu.setAttribute('aria-label', select.getAttribute('aria-label') || select.name || 'Opciones');
    const optionButtons = [...select.options].map((option) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'custom-select-option';
      item.textContent = option.textContent;
      item.dataset.value = option.value;
      item.disabled = option.disabled;
      item.setAttribute('role', 'option');
      menu.appendChild(item);
      return item;
    });
    const sync = () => {
      const selectedIndex = Math.max(select.selectedIndex, 0);
      trigger.textContent = select.options[selectedIndex]?.textContent || 'Seleccionar';
      optionButtons.forEach((item, index) => {
        const active = index === select.selectedIndex;
        item.classList.toggle('selected', active);
        item.setAttribute('aria-selected', String(active));
      });
    };
    const open = () => {
      if (trigger.disabled) return;
      if (openCustomSelect && openCustomSelect !== wrapper) closeCustomSelect();
      wrapper.classList.add('open');
      trigger.setAttribute('aria-expanded', 'true');
      openCustomSelect = wrapper;
      requestAnimationFrame(() => menu.querySelector('.selected')?.scrollIntoView({block: 'nearest'}));
    };
    const choose = (index) => {
      const option = select.options[index];
      if (!option || option.disabled) return;
      select.selectedIndex = index;
      sync();
      select.dispatchEvent(new Event('change', {bubbles: true}));
      closeCustomSelect();
      trigger.focus();
    };
    optionButtons.forEach((item, index) => item.addEventListener('click', (event) => { event.stopPropagation(); choose(index); }));
    trigger.addEventListener('click', (event) => {
      event.stopPropagation();
      wrapper.classList.contains('open') ? closeCustomSelect() : open();
    });
    trigger.addEventListener('keydown', (event) => {
      const enabled = optionButtons.map((item, index) => !item.disabled ? index : null).filter((index) => index !== null);
      let position = enabled.indexOf(select.selectedIndex);
      if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault();
        if (event.key === 'Home') position = 0;
        else if (event.key === 'End') position = enabled.length - 1;
        else position = Math.min(Math.max(position + (event.key === 'ArrowDown' ? 1 : -1), 0), enabled.length - 1);
        open();
        optionButtons[enabled[position]]?.focus();
      } else if (event.key === 'Escape') closeCustomSelect();
    });
    menu.addEventListener('keydown', (event) => {
      const enabled = optionButtons.filter((item) => !item.disabled);
      const position = enabled.indexOf(document.activeElement);
      if (event.key === 'Escape') { event.preventDefault(); closeCustomSelect(); trigger.focus(); }
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        enabled[Math.min(Math.max(position + (event.key === 'ArrowDown' ? 1 : -1), 0), enabled.length - 1)]?.focus();
      }
    });
    select.classList.add('enhanced-select');
    select.addEventListener('change', sync);
    select.addEventListener('invalid', () => trigger.focus());
    select.insertAdjacentElement('afterend', wrapper);
    wrapper.append(trigger, menu);
    sync();
  });
  document.addEventListener('click', (event) => { if (!event.target.closest('.custom-select')) closeCustomSelect(); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeCustomSelect(); });

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

  const csrfToken = () => document.cookie.split('; ').find((row) => row.startsWith('csrftoken='))?.split('=')[1] || document.querySelector('[data-page-csrf]')?.value || '';
  const inlineRows = [...document.querySelectorAll('[data-inline-field]')];
  const inlineInput = (row) => row.querySelector('input:not([type="hidden"]), textarea, select');
  const closeInline = (row, restore = false) => {
    const input = inlineInput(row);
    if (restore && input) input.type === 'checkbox' ? input.checked = row.dataset.original === 'true' : input.value = row.dataset.original || '';
    row.classList.remove('editing', 'saving');
    row.querySelector('[data-inline-error]').textContent = '';
  };
  const saveInline = async (row) => {
    if (row.classList.contains('saving')) return;
    const input = inlineInput(row);
    const value = input?.type === 'checkbox' ? String(input.checked) : input?.value ?? '';
    if (value === row.dataset.original) return closeInline(row);
    row.classList.add('saving');
    setStatus('Guardando…', 'saving');
    const payload = new FormData();
    payload.set('csrfmiddlewaretoken', csrfToken()); payload.set('action', 'inline-save'); payload.set('field', row.dataset.field); payload.set('value', value);
    try {
      const response = await fetch(location.href, {method: 'POST', body: payload, headers: {'X-Requested-With': 'XMLHttpRequest'}});
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'No se pudo guardar.');
      row.dataset.original = value;
      const text = row.querySelector('[data-inline-text]');
      if (text) text.textContent = data.display;
      closeInline(row);
      setStatus('Guardado', 'saved');
      if (row.dataset.field === 'no_sleep') document.querySelector('[data-sleep-times]')?.toggleAttribute('hidden', input.checked);
    } catch (error) {
      row.classList.remove('saving');
      row.querySelector('[data-inline-error]').textContent = error.message;
      setStatus('Error · reintenta', 'error');
    }
  };
  inlineRows.forEach((row) => {
    const input = inlineInput(row);
    if (row.hasAttribute('data-auto-inline')) {
      row.dataset.original = input?.type === 'checkbox' ? String(input.checked) : input?.value || '';
      input?.addEventListener('change', () => saveInline(row));
      row.querySelector('[data-time-now]')?.addEventListener('click', () => {
        const now = new Date();
        input.value = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
        saveInline(row);
      });
      return;
    }
    const begin = () => {
      inlineRows.filter((item) => item !== row && item.classList.contains('editing')).forEach(saveInline);
      row.dataset.original = input?.type === 'checkbox' ? String(input.checked) : input?.value || '';
      row.classList.add('editing');
      (row.querySelector('.custom-select-trigger') || input)?.focus(); input?.select?.();
    };
    row.querySelector('[data-inline-display]')?.addEventListener('click', begin);
    row.querySelector('[data-inline-confirm]')?.addEventListener('click', () => saveInline(row));
    row.querySelector('[data-inline-cancel]')?.addEventListener('click', () => closeInline(row, true));
    input?.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeInline(row, true); if (event.key === 'Enter' && input.tagName !== 'TEXTAREA') { event.preventDefault(); saveInline(row); } });
  });
  document.addEventListener('pointerdown', (event) => inlineRows.filter((row) => row.classList.contains('editing') && !row.contains(event.target)).forEach(saveInline));

  document.querySelectorAll('.photo-package-input').forEach((input) => {
    input.addEventListener('change', () => {
      const slot = input.closest('.photo-slot');
      const name = slot?.querySelector('[data-file-name]');
      slot?.classList.toggle('selected', Boolean(input.files?.length));
      if (name) name.textContent = input.files?.[0]?.name || 'Seleccionar';
    });
  });
  document.querySelectorAll('[data-body-photo-form]').forEach((form) => form.querySelector('input[type="file"]')?.addEventListener('change', async () => {
    const status = document.querySelector('[data-photo-upload-status]');
    if (status) status.textContent = 'Guardando foto…';
    try {
      const response = await fetch(location.href, {method: 'POST', body: new FormData(form), headers: {'X-Requested-With': 'XMLHttpRequest'}});
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || 'No se pudo guardar.');
      form.querySelector('.photo-slot')?.classList.add('selected');
      form.querySelector('[data-file-name]').textContent = 'Guardada';
      if (status) status.textContent = `${data.count}/5 fotos guardadas`;
      const analyze = document.querySelector('[data-analyze-body]'); if (analyze) analyze.disabled = data.count !== 5;
    } catch (error) { if (status) status.textContent = error.message; }
  }));

  const gallery = document.getElementById('bodyPhotoGallery');
  document.querySelector('[data-open-gallery]')?.addEventListener('click', () => gallery?.showModal());
  document.querySelector('[data-close-gallery]')?.addEventListener('click', () => gallery?.close());
  gallery?.addEventListener('click', (event) => { if (event.target === gallery) gallery.close(); });

  const mealDialog = document.getElementById('mealDialog');
  const supplementDialog = document.getElementById('supplementDialog');
  const activityDialog = document.getElementById('activityDialog');
  document.querySelector('[data-open-meal]')?.addEventListener('click', () => mealDialog?.showModal());
  document.querySelector('[data-open-supplement]')?.addEventListener('click', () => supplementDialog?.showModal());
  document.querySelector('[data-open-activity]')?.addEventListener('click', () => activityDialog?.showModal());
  document.querySelector('[data-open-body-photos]')?.addEventListener('click', () => document.getElementById('bodyPhotoDialog')?.showModal());
  if (mealDialog?.hasAttribute('data-open-on-load')) mealDialog.showModal();
  if (activityDialog?.hasAttribute('data-open-on-load')) activityDialog.showModal();
  document.querySelectorAll('[data-close-dialog]').forEach((button) => button.addEventListener('click', () => button.closest('dialog')?.close()));
  document.querySelectorAll('.entry-dialog').forEach((dialog) => dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); }));

  const activityCategory = activityDialog?.querySelector('[name="category"]');
  const activityAmount = activityDialog?.querySelector('[name="amount"]');
  const activityAmountLabel = activityDialog?.querySelector('[data-activity-amount-label]');
  const activityUnit = activityDialog?.querySelector('[data-activity-unit]');
  const syncActivityAmount = () => {
    const quantity = {steps: ['Cantidad de pasos', 'pasos'], pushups: ['Cantidad de lagartijas', 'repeticiones']};
    const duration = {functional_moderate: 'Funcional moderado', functional_intense: 'Funcional intenso', gym: 'Gimnasio'};
    const config = quantity[activityCategory?.value] || (duration[activityCategory?.value] ? ['Duración', 'minutos'] : ['Tiempo o cantidad', 'Selecciona el tipo de actividad']);
    if (activityAmountLabel) activityAmountLabel.textContent = config[0];
    if (activityUnit) activityUnit.textContent = config[1];
    if (activityAmount) {
      activityAmount.placeholder = quantity[activityCategory?.value] ? '0' : 'Minutos';
      activityAmount.step = quantity[activityCategory?.value] ? '1' : '0.01';
    }
  };
  activityCategory?.addEventListener('change', syncActivityAmount);
  syncActivityAmount();

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

  const noSleep = document.querySelector('[data-field="no_sleep"] input[name="no_sleep"]');
  const sleepTimes = document.querySelector('[data-sleep-times]');
  const syncSleepTimes = () => {
    if (!sleepTimes || !noSleep) return;
    sleepTimes.hidden = noSleep.checked;
  };
  noSleep?.addEventListener('change', syncSleepTimes);
  syncSleepTimes();

  document.querySelector('[data-breakdown-toggle]')?.addEventListener('click', (event) => {
    const summary = event.currentTarget.closest('.sticky-summary');
    summary.classList.toggle('mobile-open');
    event.currentTarget.textContent = summary.classList.contains('mobile-open') ? 'Ocultar desglose' : 'Ver desglose';
  });

  window.setTimeout(() => document.querySelectorAll('.message').forEach(el => el.remove()), 4200);
})();
