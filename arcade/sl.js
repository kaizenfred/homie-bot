/* Shared look + score plumbing for every SpreadLight arcade game.
   Each game is self-contained otherwise. */

const SL = (() => {
  const params = new URLSearchParams(location.search);
  const token = params.get("t") || "";
  const game = params.get("g") || "";
  let sent = 0;

  /* Telegram's games.js is present when launched from a chat. */
  const tg = window.TelegramGameProxy;

  async function submit(score) {
    score = Math.max(0, Math.floor(score));
    if (!token || score <= sent) return;
    sent = score;
    try {
      await fetch("../score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ t: token, g: game, score }),
      });
    } catch (e) { /* offline: the run still counts locally */ }
  }

  function share() { if (tg && tg.shareScore) tg.shareScore(); }

  /* input: keyboard + touch, since most of the fam is on a phone */
  function input() {
    const st = { left: false, right: false, up: false, down: false, fire: false };
    const map = {
      ArrowLeft: "left", KeyA: "left", ArrowRight: "right", KeyD: "right",
      ArrowUp: "up", KeyW: "up", ArrowDown: "down", KeyS: "down",
      Space: "fire",
    };
    addEventListener("keydown", e => {
      if (map[e.code]) { st[map[e.code]] = true; e.preventDefault(); }
    });
    addEventListener("keyup", e => {
      if (map[e.code]) { st[map[e.code]] = false; e.preventDefault(); }
    });
    return st;
  }

  /* drag anywhere on the canvas to steer; tap to fire */
  function touch(canvas, onMove, onTap) {
    let moved = false;
    const pos = e => {
      const r = canvas.getBoundingClientRect();
      const t = e.touches ? e.touches[0] : e;
      return {
        x: (t.clientX - r.left) * (canvas.width / r.width),
        y: (t.clientY - r.top) * (canvas.height / r.height),
      };
    };
    canvas.addEventListener("touchstart", e => {
      moved = false; onMove(pos(e)); e.preventDefault();
    }, { passive: false });
    canvas.addEventListener("touchmove", e => {
      moved = true; onMove(pos(e)); e.preventDefault();
    }, { passive: false });
    canvas.addEventListener("touchend", e => {
      if (!moved && onTap) onTap(); e.preventDefault();
    }, { passive: false });
    canvas.addEventListener("mousemove", e => onMove(pos(e)));
    canvas.addEventListener("click", () => onTap && onTap());
  }

  /* fit a fixed-logic-size canvas into the viewport without distortion */
  function fit(canvas) {
    const scale = () => {
      const pad = 16;
      const w = innerWidth - pad * 2;
      const h = innerHeight - 90;
      const s = Math.min(w / canvas.width, h / canvas.height);
      canvas.style.width = canvas.width * s + "px";
      canvas.style.height = canvas.height * s + "px";
    };
    addEventListener("resize", scale);
    scale();
  }

  return { submit, share, input, touch, fit, game };
})();
