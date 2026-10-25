(() => {
  'use strict';
  const find = selector => document.querySelector(selector);
  const token = new URL(location.href).searchParams.get('token');
  const note = find('#note'), submit = find('#submit'), batchViews = new Map();
  const encoder = new TextEncoder();
  let state, displayedScreen, latestReplyId, sending = false, polling = false, online = false, pending;
  const labels = { clear: 'Mer luft', compact: 'Kompakt oversikt', guided: 'Ett steg om gangen' };
  const setText = (element, value) => { if (element.textContent !== value) element.textContent = value; };
  const error = message => { setText(find('#error'), message); find('#error').hidden = !message; };
  const tooLong = value => encoder.encode(value).length > 2000;
  function fieldError(message) {
    setText(find('#note-error'), message);
    find('#note-error').hidden = !message;
    const invalid = message ? 'true' : 'false';
    if (note.getAttribute('aria-invalid') !== invalid) note.setAttribute('aria-invalid', invalid);
  }
  function validateNote() {
    const invalid = tooLong(note.value);
    fieldError(invalid ? 'Innspillet er for langt. Kort ned teksten før du sender.' : '');
    return !invalid;
  }
  function available() {
    submit.disabled = !online || !state || sending || (!pending && !note.value.trim()) || state.batches.some(batch => ['sending', 'unknown'].includes(batch.delivery) && batch.review === 'unread');
    setText(submit, pending ? 'Avklar forrige innsending' : 'Send innspill');
  }
  function receipt(batch) {
    if (batch.review === 'resolved') return 'Besvart';
    if (batch.review === 'working') return 'Under behandling';
    if (batch.delivery === 'queued') return 'Lagt i samtalens kø';
    if (batch.delivery === 'unknown') return 'Levering uavklart';
    return 'Sender til samtalen …';
  }
  function renderBatches(batches) {
    const changes = [], present = new Set();
    batches.forEach((batch, index) => {
      present.add(batch.id);
      const status = receipt(batch);
      let view = batchViews.get(batch.id);
      if (!view) {
        const article = document.createElement('article'); article.className = 'batch'; article.dataset.batch = batch.id; article.id = `round-${batch.id}`; article.tabIndex = -1;
        const heading = document.createElement('h3'), detail = document.createElement('p'), content = document.createElement('p'), reply = document.createElement('p'), help = document.createElement('p');
        heading.id = `round-heading-${batch.id}`; article.setAttribute('aria-labelledby', heading.id);
        detail.className = 'help'; reply.className = 'reply'; help.className = 'error';
        article.append(heading, detail, content, reply, help);
        find('#batches').append(article);
        view = { article, heading, detail, content, reply, help };
        batchViews.set(batch.id, view);
      }
      if (batch.reply && view.replyText !== batch.reply) latestReplyId = batch.id;
      if (view.status !== status) changes.push(`Runde ${index + 1}: ${status}`);
      else if (batch.reply && view.replyText !== batch.reply) changes.push(`Runde ${index + 1} har et oppdatert svar.`);
      setText(view.heading, `Runde ${index + 1} · ${status}`);
      setText(view.detail, `${labels[batch.choice]} · skisseversjon ${batch.screen}`);
      setText(view.content, batch.note);
      setText(view.reply, batch.reply); view.reply.hidden = !batch.reply;
      const uncertain = batch.delivery === 'unknown' && batch.review === 'unread';
      setText(view.help, uncertain ? 'Kontroller samtalen før du sender på nytt. Prøven sender ikke automatisk en gang til.' : ''); view.help.hidden = !uncertain;
      view.status = status; view.replyText = batch.reply;
    });
    for (const [id, view] of batchViews) if (!present.has(id)) { view.article.remove(); batchViews.delete(id); }
    if (changes.length) setText(find('#review-status'), changes.join(' '));
    const link = find('#latest-reply-link');
    const latestReply = batchViews.get(latestReplyId)?.article;
    link.hidden = !latestReply;
    if (latestReply) link.setAttribute('href', `#${latestReply.id}`);
  }
  function render(next) {
    if (state && next.revision < state.revision) return;
    state = next;
    if (pending && next.batches.some(batch => batch.id === pending.requestId)) {
      if (note.value === pending.note) note.value = '';
      pending = undefined;
      error(''); validateNote();
      setText(find('#notice'), 'Innsendingen er funnet igjen. Leveringsstatus vises nedenfor.');
    }
    if (!displayedScreen || (!note.value && !pending)) {
      displayedScreen = next.screen;
      setText(find('#title'), next.document.title);
      setText(find('#description'), next.document.description);
      setText(find('#sample-title'), next.document.title);
      setText(find('#sample-description'), next.document.description);
    }
    setText(find('#version'), `Skisseversjon ${displayedScreen}`);
    const newer = next.screen !== displayedScreen;
    find('#update').hidden = !newer;
    setText(find('#update'), newer ? `En ny skisse er klar. Utkastet gjelder versjon ${displayedScreen}. Send eller tøm utkastet for å se den nye skissen.` : '');
    renderBatches(next.batches);
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
    try { render(await request('/api/state')); online = true; setText(find('#connection'), 'Tilkoblet'); }
    catch { online = false; setText(find('#connection'), 'Frakoblet – behold utkastet'); }
    finally { polling = false; available(); }
  }
  note.addEventListener('input', () => { validateNote(); if (!note.value && state) render(state); available(); });
  document.querySelectorAll('[name=choice]').forEach(input => input.addEventListener('change', () => { find('.surface').dataset.choice = input.value; }));
  find('#read').addEventListener('click', refresh);
  document.querySelectorAll('.shortcuts a').forEach(link => link.addEventListener('click', event => {
    const target = find(link.getAttribute('href'));
    if (target) { event.preventDefault(); target.focus(); target.scrollIntoView({ block: 'center' }); }
  }));
  submit.addEventListener('click', async () => {
    if (submit.disabled) return;
    if (!pending && !validateNote()) { note.focus(); return; }
    pending = pending || { expectedRevision: state.revision, screen: displayedScreen, requestId: crypto.randomUUID(), choice: find('[name=choice]:checked').value, note: note.value };
    const submitted = pending;
    sending = true; error(''); available();
    try {
      const result = await request('/api/submit', submitted); render(result.snapshot);
      setText(find('#notice'), 'Runden er lagret i denne prøveøkten. Leveringsstatus vises nedenfor; en kvittering betyr ikke at innspillet er behandlet.');
    } catch (failure) {
      if (state?.batches.some(batch => batch.id === submitted.requestId)) error('');
      else if (failure.status) {
        pending = undefined;
        if (failure.status === 400) { fieldError('Innspillet kunne ikke lagres. Se gjennom teksten og prøv igjen.'); note.focus(); }
        else error(failure.message);
      } else error('Svaret kom ikke fram. Utkastet er beholdt. Oppdater status før du gjør noe mer.');
      await refresh();
    } finally { sending = false; available(); }
  });
  void refresh();
  setInterval(refresh, 1500);
})();
