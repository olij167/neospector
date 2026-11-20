(function () {
  'use strict';
  const root = '/downloads/neospector/';
  const content = JSON.parse(document.getElementById('site-data').textContent);
  const $ = id => document.getElementById(id);
  $('site-title').textContent = content.product || 'Neospector';
  $('eyebrow').textContent = content.eyebrow || '';
  $('site-description').textContent = content.description || '';
  $('site-detail').textContent = content.detail || '';
  $('download-title').textContent = content.download_heading || 'Download Neospector';
  $('public-test-note').textContent = content.public_test_notice || '';
  const commerce = content.commerce || {};
  if (commerce.enabled === true && /^https:\/\//.test(commerce.url || '')) {
    const link = document.createElement('a');
    link.href = commerce.url; link.rel = 'noopener noreferrer';
    link.textContent = commerce.label || 'Purchase Neospector';
    $('commerce').replaceChildren(link); $('commerce').hidden = false;
  }
  const media = (Array.isArray(content.media) ? content.media : []).filter(item =>
    item && (item.type === 'image' || item.type === 'video') &&
    typeof item.src === 'string' &&
    (/^\/downloads\/neospector\/media\/[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(item.src) ||
      /^https:\/\/[A-Za-z0-9.-]+\/[A-Za-z0-9/?=&_.%-]+$/.test(item.src)));
  let slideIndex = 0;
  let timer = null;
  const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function clearTimer() { if (timer !== null) { clearTimeout(timer); timer = null; } }
  function showMedia(index) {
    clearTimer(); if (!media.length) return;
    slideIndex = (index + media.length) % media.length;
    const item = media[slideIndex];
    const el = document.createElement(item.type === 'video' ? 'video' : 'img');
    el.src = item.src;
    if (item.type === 'image') { el.alt = item.alt || ''; el.loading = 'eager'; }
    else { el.controls = true; el.preload = 'metadata'; el.playsInline = true; if (item.poster) el.poster = item.poster; }
    $('media-frame').replaceChildren(el);
    $('media-caption').textContent = (item.caption || '') + (media.length > 1 ? '  ' + (slideIndex + 1) + '/' + media.length : '');
    $('media-controls').hidden = media.length <= 1 && !item.caption;
    if (media.length > 1 && item.type === 'image' && !reduceMotion) {
      const ms = Math.max(3, Math.min(30, Number(content.media_interval_seconds) || 7)) * 1000;
      timer = setTimeout(() => { if (!document.hidden) showMedia(slideIndex + 1); }, ms);
    }
  }
  if (media.length) showMedia(0);
  $('media-prev').addEventListener('click', () => showMedia(slideIndex - 1));
  $('media-next').addEventListener('click', () => showMedia(slideIndex + 1));
  document.addEventListener('visibilitychange', () => { if (document.hidden) clearTimer(); else if (media.length) showMedia(slideIndex); });
  $('media-frame').addEventListener('mouseenter', clearTimer);
  $('media-frame').addEventListener('mouseleave', () => { if (media.length && media[slideIndex].type === 'image') showMedia(slideIndex); });

  const cache = {};
  const downloadButton = $('primary-download');
  const options = Array.from(document.querySelectorAll('input[name="download-os"]'));
  const display = {
    linux: {label:'Linux', extension:'64-bit · DEB installer'},
    windows: {label:'Windows', extension:'64-bit · EXE installer'},
    macos: {label:'macOS', extension:'PKG installer'}
  };
  const formatSize = bytes => Number.isSafeInteger(bytes) && bytes > 0 ? ' · ' + (bytes / 1048576).toFixed(1) + ' MiB' : '';
  const valid = r => r && r.ready === true && typeof r.key === 'string' &&
    /Neospector_[A-Za-z0-9_.-]+\.(deb|exe|pkg)$/.test(r.key.split('/').pop()) &&
    /^[0-9a-f]{64}$/i.test(r.sha256 || '') && Number.isSafeInteger(r.bytes) && r.bytes > 0;
  function suggestedOS() {
    const agent = (navigator.userAgent || '').toLowerCase();
    // Mobile devices are not supported, even when their UA mentions Linux/Mac.
    if (/android|iphone|ipad|ipod/.test(agent)) return null;
    const platform = (navigator.userAgentData?.platform || navigator.platform || '').toLowerCase();
    if (platform.includes('win') || agent.includes('windows nt')) return 'windows';
    if (platform.includes('mac') || agent.includes('macintosh')) return 'macos';
    if (platform.includes('linux') || platform.includes('x11') || agent.includes('x11; linux')) return 'linux';
    return null;
  }
  const detected = suggestedOS();
  if (detected) $('os-' + detected).checked = true;
  let catalogueLoaded = false;
  function choice() { return options.find(input => input.checked)?.value || null; }
  function selectedAlias() {
    const selected = choice();
    if (selected === 'linux') return 'linux';
    if (selected === 'windows') return 'windows-x64';
    return null;
  }
  function macAlias(architecture) {
    return cache[architecture + '-pkg'] ? architecture + '-pkg' : (cache[architecture] ? architecture : null);
  }
  function setLink(link, alias) {
    link.removeAttribute('href');
    link.removeAttribute('download');
    link.setAttribute('aria-disabled', 'true');
    if (catalogueLoaded && alias && cache[alias]) {
      link.href = root + 'files/latest/' + alias;
      link.setAttribute('download', '');
      link.setAttribute('aria-disabled', 'false');
    }
  }
  function renderDownload() {
    const selected = choice();
    $('mac-downloads').hidden = selected !== 'macos';
    downloadButton.hidden = selected === 'macos';
    setLink(downloadButton, selectedAlias());
    setLink($('mac-download-arm64'), macAlias('macos-arm64'));
    setLink($('mac-download-x64'), macAlias('macos-x64'));
    for (const [id,arch,label] of [['mac-download-arm64','macos-arm64','M-series · PKG'],['mac-download-x64','macos-x64','Intel Mac · PKG']]) {
      const alias = macAlias(arch);
      $(id).querySelector('small').textContent = label + (alias && cache[alias] ? formatSize(cache[alias].bytes) : '');
    }
    if (selected === 'macos') {
      if (!catalogueLoaded) {
        $('selection-hint').textContent = 'Checking macOS installers…';
      } else {
        const armReady = $('mac-download-arm64').getAttribute('aria-disabled') === 'false';
        const intelReady = $('mac-download-x64').getAttribute('aria-disabled') === 'false';
        $('selection-hint').textContent = !armReady && !intelReady
          ? 'macOS installers are currently unavailable.'
          : armReady && intelReady
            ? 'Choose the installer for your Mac processor.'
            : 'Unavailable architectures are disabled. Choose the installer for your Mac processor.';
      }
      return;
    }
    if (!selected) {
      $('download-action').textContent = 'Choose an operating system';
      $('download-subtitle').textContent = 'Linux · Windows · macOS';
      $('selection-hint').textContent = 'Select the operating system of the computer where you will install Neospector.';
      return;
    }
    $('download-action').textContent = 'Download for ' + display[selected].label;
    const available = selectedAlias() && cache[selectedAlias()];
    $('download-subtitle').textContent = display[selected].extension + (available ? formatSize(available.bytes) : '');
    if (!catalogueLoaded) {
      $('selection-hint').textContent = 'Checking installer availability…';
      return;
    }
    if (downloadButton.getAttribute('aria-disabled') === 'true') {
      $('download-action').textContent = display[selected].label + ' installer unavailable';
      $('selection-hint').textContent = 'That installer is currently unavailable. Select another operating system or check back later.';
      return;
    }
    $('selection-hint').textContent = 'Installer for ' + display[selected].label + '. Other operating systems are available above.';
  }
  for (const option of options) option.addEventListener('change', renderDownload);
  for (const link of [downloadButton, $('mac-download-arm64'), $('mac-download-x64')]) {
    link.addEventListener('click', event => {
      if (link.getAttribute('aria-disabled') === 'true') event.preventDefault();
    });
  }
  function failure() {
    $('version').textContent = 'Unavailable'; $('release-stage').textContent = 'Could not verify the current public release.';
    catalogueLoaded = false;
    renderDownload();
    $('selection-hint').textContent = 'Release information could not be verified. Downloads are temporarily disabled.';
  }
  renderDownload();
  fetch(root + 'releases.json', {cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Catalogue request failed');return r.json();}).then(data=>{
    if(!data || !/^\d+\.\d+\.\d+$/.test(data.version || '') || !data.downloads) throw Error('Invalid catalogue');
    $('version').textContent = 'v' + data.version;
    $('release-stage').textContent = data.release_stage === 'public-test' ? 'Public test release' : 'Latest release';
    for (const alias of ['linux','windows-x64','macos-arm64','macos-x64','macos-arm64-pkg','macos-x64-pkg']) {
      if(valid(data.downloads[alias])) cache[alias] = data.downloads[alias];
    }
    catalogueLoaded = true; renderDownload();


  }).catch(failure);
  // feedback-console-v2: no payment, tracking SDK, local storage or file upload.
  (function feedbackConsole(){
    const conf=content.feedback||{};
    const form=$('neo-feedback-form'),status=$('neo-feedback-status');
    if(!form)return;
    const submit=$('neo-feedback-submit'),message=$('neo-feedback-message'),count=$('neo-feedback-count');
    let widgetId=null,loaded=false,busy=false,verified=false;
    const setStatus=(s,error=false)=>{status.textContent=s;status.dataset.error=error?'true':'false';};
    const ready=()=>{submit.disabled=busy||!verified;};
    message.addEventListener('input',()=>{count.textContent=message.value.length+' / 5000';});
    if(conf.enabled!==true||!/^[A-Za-z0-9_-]{15,100}$/.test(conf.turnstile_sitekey||'')){
      form.querySelectorAll('input,textarea,select,button').forEach(el=>el.disabled=true);
      setStatus('Feedback submissions are temporarily unavailable.');return;
    }
    const script=document.createElement('script');script.async=true;
    script.src='https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
    script.onload=()=>{
      if(!window.turnstile){setStatus('Verification unavailable.',true);return;}
      try{widgetId=window.turnstile.render('#neo-feedback-turnstile',{
        sitekey:conf.turnstile_sitekey,action:'neospector-feedback',theme:'auto',size:'flexible',
        callback:()=>{verified=true;ready();setStatus('Ready to send.')},
        'expired-callback':()=>{verified=false;ready();setStatus('Verification expired. Please try again.')},
        'error-callback':()=>{verified=false;ready();setStatus('Verification unavailable. Please retry.',true)}
      });loaded=true;}catch{setStatus('Could not initialize verification.',true);}
    };
    script.onerror=()=>setStatus('Could not load verification. Please retry later.',true);
    document.head.append(script);
    form.addEventListener('submit',async ev=>{
      ev.preventDefault();if(busy||!loaded)return;
      const raw=message.value.trim(),email=$('neo-feedback-email').value.trim();
      if(raw.length<10||raw.length>5000||(email&&!$('neo-feedback-email').checkValidity())){
        setStatus('Please enter 10–5000 characters and check the reply email.',true);return;
      }
      const token=window.turnstile?.getResponse(widgetId);
      if(!token){setStatus('Complete verification before sending.',true);return;}
      busy=true;ready();setStatus('Sending report…');
      try{
        const platform=Array.from(document.querySelectorAll('input[name="download-os"]')).find(e=>e.checked)?.value||'unknown';
        const releaseVersion=$('version')?.textContent?.trim()||'';
        const response=await fetch('/api/neospector/feedback',{method:'POST',headers:{'content-type':'application/json'},
          body:JSON.stringify({kind:$('neo-feedback-kind').value,message:raw,email,platform,version:releaseVersion,
            website:$('neo-feedback-website').value,turnstile_token:token})});
        const result=await response.json();
        if(!response.ok||result.ok!==true||!/^NS-[a-f0-9-]{36}$/i.test(result.id||''))throw Error(result.error||'Submission failed.');
        form.reset();count.textContent='0 / 5000';setStatus('Feedback received. Reference: '+result.id);
      }catch(error){setStatus('Could not send feedback: '+String(error.message||'Try again.'),true);}
      finally{busy=false;verified=false;ready();if(loaded&&widgetId!==null)window.turnstile.reset(widgetId);}
    });
  })();

})();
