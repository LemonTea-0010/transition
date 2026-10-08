"""Popup copy is fixed; presentation follows the current saved page."""

from .tasks import Task

POPUP_ID = "transition-exp-popup"


def popup_config(task: Task, condition: str) -> dict:
    timing, relevance = condition.split("_", 1)
    title, body, button = task.low if relevance == "low" else task.high
    return {"title": title, "body": body, "button": button,
            "condition": timing, "relevance": relevance,
            "page": task.page,
            "popup_id": f"{task.page}_{condition}_v1"}


def inject_popup(page, config: dict) -> bool:
    # textContent prevents saved-page content or copy from becoming markup.
    return bool(page.evaluate("""(cfg) => {
      if (document.getElementById('transition-exp-popup')) return false;
      const selectors = {
        taobao: {surface: '.tbpc-col', accent: '.search-button', text: '.item-title'},
        ctrip: {surface: '.hotel-card', accent: 'button', text: '.hotel-card'},
        bilibili: {surface: '.bili-video-card', accent: 'button', text: '.bili-video-card'},
        amazon: {surface: 'div[class*="ProductCard-module__card_"]', accent: 'input[type="submit"]', text: 'body'}
      };
      const sample = selectors[cfg.page] || {};
      const style = (selector) => {
        const element = selector && document.querySelector(selector);
        return element ? getComputedStyle(element) : null;
      };
      const root = getComputedStyle(document.body);
      const surface = style(sample.surface);
      const textStyle = style(sample.text);
      const accent = style(sample.accent);
      const visible = (value) => value && value !== 'transparent' && value !== 'rgba(0, 0, 0, 0)';
      const brand = {taobao:'#ff5000', ctrip:'#0086f6', bilibili:'#fb7299', amazon:'#ffd814'}[cfg.page];
      const background = visible(surface?.backgroundColor) ? surface.backgroundColor :
        (visible(root.backgroundColor) ? root.backgroundColor : '#fff');
      const foreground = visible(textStyle?.color) ? textStyle.color :
        (visible(root.color) ? root.color : '#222');
      const accentColor = cfg.page === 'bilibili' ? brand :
        (visible(accent?.backgroundColor) ? accent.backgroundColor : brand);
      const buttonText = cfg.page === 'amazon' ? '#0f1111' : '#fff';
      const overlay = document.createElement('div');
      overlay.id = 'transition-exp-popup';
      overlay.setAttribute('role', 'dialog');
      overlay.setAttribute('aria-modal', 'true');
      Object.assign(overlay.style, {
        position:'fixed', inset:'0', zIndex:'2147483646',
        background:'rgba(0,0,0,.42)', display:'flex',
        alignItems:'center', justifyContent:'center', pointerEvents:'auto'
      });
      const card = document.createElement('div');
      Object.assign(card.style, {
        boxSizing:'border-box', width:'440px', height:'240px',
        padding:'28px', border:'1px solid ' + (surface?.borderColor || '#d8d8d8'),
        borderRadius:surface?.borderRadius || '10px',
        background, boxShadow:'0 14px 38px rgba(0,0,0,.24)',
        fontFamily:root.fontFamily, color:foreground,
        display:'flex', flexDirection:'column'
      });
      const title = document.createElement('div');
      title.textContent = cfg.title;
      Object.assign(title.style, {fontSize:'20px', fontWeight:'600', lineHeight:'28px'});
      const body = document.createElement('div');
      body.textContent = cfg.body;
      Object.assign(body.style, {fontSize:'16px', lineHeight:'24px', whiteSpace:'pre-line',
        marginTop:'18px', flex:'1'});
      const button = document.createElement('button');
      button.id = 'exp-popup-primary';
      button.textContent = cfg.button;
      Object.assign(button.style, {alignSelf:'flex-end', boxSizing:'border-box',
        width:'100px', height:'38px', border:'0', borderRadius:'5px',
        background:accentColor, color:buttonText, fontFamily:root.fontFamily,
        fontSize:'15px', cursor:'pointer'});
      window.__popup_state = {shown:true, clicked:false,
        condition:cfg.condition, relevance:cfg.relevance,
        popup_id:cfg.popup_id, shown_at:Date.now()};
      const blockWheel = (event) => event.preventDefault();
      const blockKeys = (event) => {
        if (['Tab', 'Escape', 'PageDown', 'PageUp', 'ArrowDown', 'ArrowUp',
             'Home', 'End', ' '].includes(event.key)) {
          if (event.key !== 'Tab') event.preventDefault();
          if (event.key === 'Tab') button.focus();
          event.stopPropagation();
        }
      };
      document.addEventListener('wheel', blockWheel, {capture:true, passive:false});
      document.addEventListener('touchmove', blockWheel, {capture:true, passive:false});
      document.addEventListener('keydown', blockKeys, true);
      button.addEventListener('click', () => {
        window.__popup_state.clicked = true;
        document.removeEventListener('wheel', blockWheel, true);
        document.removeEventListener('touchmove', blockWheel, true);
        document.removeEventListener('keydown', blockKeys, true);
        overlay.remove();
      });
      card.append(title, body, button);
      overlay.append(card);
      document.body.append(overlay);
      button.focus();
      return true;
    }""", config))


def popup_state(page) -> dict:
    return page.evaluate("window.__popup_state || {shown:false, clicked:false}")
