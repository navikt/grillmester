(() => {
  'use strict';
  const find = selector => document.querySelector(selector);
  const token = new URL(location.href).searchParams.get('token');
  const note = find('#note'), submit = find('#submit');
  let state, displayedScreen, batchesKey, sending = false, polling = false, online = false, pending;
  const labels = { clear: 'Mer luft', compact: 'Kompakt oversikt', guided: 'Ett steg om gangen' };
  const error = message => { find('#error').textContent = message; find('#error').hidden = !message; };
  function available() {
    submit.disabled = !online || !state || sending || !note.value.trim() || state.batches.some(batch => ['sending', 'unknown'].includes(batch.delivery) && batch.review === 'unread');
    submit.textContent = pending ? 'Avklar forrige innsending' : 'Send innspill';
  }
  function receipt(batch) {
    if (batch.review === 'resolved') return 'Besvart';
    if (batch.review === 'working') return 'Under behandling';
    if (batch.delivery === 'queued') return 'Lagt i samtalens kø';
    if (batch.delivery === 'unknown') return 'Levering uavklart';
    return 'Sender til samtalen …';
  }
  function render(next) {
    if (state && next.revision < state.revision) return;
    state = next;
    if (pending && next.batches.some(batch => batch.id === pending.requestId)) {
      if (note.value === pending.note) note.value = '';
      pending = undefined;
      error('');
      find('#notice').textContent = 'Innsendingen er funnet igjen. Leveringsstatus vises nedenfor.';
    }
    if (!displayedScreen || (!note.value && !pending)) {
      displayedScreen = next.screen;
      find('#title').textContent = next.document.title;
      find('#description').textContent = next.document.description;
      find('#sample-title').textContent = next.document.title;
      find('#sample-description').textContent = next.document.description;
    }
    find('#version').textContent = `Skisseversjon ${displayedScreen}`;
    const newer = next.screen !== displayedScreen;
    find('#update').hidden = !newer;
    find('#update').textContent = newer ? `En ny skisse er klar. Utkastet gjelder versjon ${displayedScreen}. Send eller tøm utkastet for å se den nye skissen.` : '';
    const nextBatchesKey = JSON.stringify(next.batches);
    if (nextBatchesKey !== batchesKey) find('#batches').replaceChildren(...next.batches.map((batch, index) => {
      const article = document.createElement('article'); article.className = 'batch'; article.dataset.batch = batch.id;
      const heading = document.createElement('h3'); heading.textContent = `Runde ${index + 1} · ${receipt(batch)}`;
      const detail = document.createElement('p'); detail.className = 'help'; detail.textContent = `${labels[batch.choice]} · skisseversjon ${batch.screen}`;
      const content = document.createElement('p'); content.textContent = batch.note;
      article.append(heading, detail, content);
      if (batch.reply) { const reply = document.createElement('p'); reply.className = 'reply'; reply.textContent = batch.reply; article.append(reply); }
      if (batch.delivery === 'unknown' && batch.review === 'unread') { const help = document.createElement('p'); help.className = 'error'; help.textContent = 'Kontroller samtalen før du sender på nytt. Prøven sender ikke automatisk en gang til.'; article.append(help); }
      return article;
    }));
    batchesKey = nextBatchesKey;
    available();
  }
  async function request(path, body) {
    const url = new URL(path, location.href); url.searchParams.set('token', token);
    const response = await fetch(url, { cache: 'no-store', signal: AbortSignal.timeout(5000), ...(body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) });
    const result = await response.json();
    if (!response.ok) throw Object.assign(new Error(result.error || 'Handlingen mislyktes.'), { status: response.status });
    return result;
  }
  async function refresh() {
    if (polling) return;
    polling = true;
    try { render(await request('/api/state')); online = true; find('#connection').textContent = 'Tilkoblet'; }
    catch { online = false; find('#connection').textContent = 'Frakoblet – behold utkastet'; }
    finally { polling = false; available(); }
  }
  note.addEventListener('input', () => { if (!note.value && state) render(state); available(); });
  document.querySelectorAll('[name=choice]').forEach(input => input.addEventListener('change', () => { find('.surface').dataset.choice = input.value; }));
  find('#read').addEventListener('click', refresh);
  submit.addEventListener('click', async () => {
    if (submit.disabled) return;
    pending = pending || { expectedRevision: state.revision, screen: displayedScreen, requestId: crypto.randomUUID(), choice: find('[name=choice]:checked').value, note: note.value };
    const submitted = pending;
    sending = true; error(''); available();
    try {
      const result = await request('/api/submit', submitted); render(result.snapshot);
      find('#notice').textContent = 'Runden er lagret i denne prøveøkten. Leveringsstatus vises nedenfor; en kvittering betyr ikke at innspillet er behandlet.';
    } catch (failure) {
      if (state?.batches.some(batch => batch.id === submitted.requestId)) error('');
      else if (failure.status) { pending = undefined; error(failure.message); }
      else error('Svaret kom ikke fram. Utkastet er beholdt. Oppdater status før du gjør noe mer.');
      await refresh();
    } finally { sending = false; available(); }
  });
  void refresh();
  setInterval(refresh, 1500);
})();
