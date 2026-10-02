// A phone's / tablet's screen doesn't turn off while the page shows - always, no setting (the user); Android and iOS only
// (a PC: no "playing audio" on its tab, its screen left alone). The screen wake
// lock where the browser offers it (a secure page only: https - a map shared over the internet -, localhost), else
// NoSleep.js's trick: a tiny video looping, in the page but off screen (phones stay awake while a video plays; a video
// not in the page: no effect - NoSleep's note, "iOS > 15: needs to be on the document"). Not muted: Chrome keeps the
// screen on for a video only if it's audible - an audio track, volume > 0 (silence counts) - or seen - 75 % of it on
// screen, a fifth of the screen big (blink's video_wake_lock.cc; muted, Android's screen went off: the user). The video
// is in here (a data URI): Safari plays a video from a server only by byte ranges, and ours sends none. 16 x 16 black,
// 2 s, H.264 baseline + a silent AAC track. (Playing "audio", Android may lower other apps' music meanwhile.)
// A video's first play needs a tap (unmuted: always - no page may start sound by itself): any tap on the page is one -
// the first after opening it, or after coming back to it if the phone paused the video. Both stop while the page is
// hidden: taken again when it's back.

const CLIP = "data:video/mp4;base64," +
  "AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAWYbW9vdgAAAGxtdmhkAAAAAAAAAAAAAAAAAAAD6AAACFAAAQAAAQAAAAAAAAAAAAAA" +
  "AAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAwAAAkV0cmFrAAAAXHRraGQAAAAD" +
  "AAAAAAAAAAAAAAABAAAAAAAAB9AAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAABAAAAAQAAAAAAAk" +
  "ZWR0cwAAABxlbHN0AAAAAAAAAAEAAAfQAAAAAAABAAAAAAG9bWRpYQAAACBtZGhkAAAAAAAAAAAAAAAAAABAAAAAgABVxAAAAAAALWhkbHIAAAAA" +
  "AAAAAHZpZGUAAAAAAAAAAAAAAABWaWRlb0hhbmRsZXIAAAABaG1pbmYAAAAUdm1oZAAAAAEAAAAAAAAAAAAAACRkaW5mAAAAHGRyZWYAAAAAAAAA" +
  "AQAAAAx1cmwgAAAAAQAAAShzdGJsAAAApHN0c2QAAAAAAAAAAQAAAJRhdmMxAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAABAAEABIAAAASAAAAAAA" +
  "AAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGP//AAAALmF2Y0MBQsAe/+EAFmdCwB7ZHsBEAAADAAQAAAMACDxYuSABAAVoy4PE" +
  "yAAAABBwYXNwAAAAAQAAAAEAAAAYc3R0cwAAAAAAAAABAAAAAgAAQAAAAAAUc3RzcwAAAAAAAAABAAAAAQAAABxzdHNjAAAAAAAAAAEAAAABAAAA" +
  "AQAAAAEAAAAcc3RzegAAAAAAAAAAAAAAAgAAAokAAAALAAAAGHN0Y28AAAAAAAAAAgAABd0AAAiGAAACfXRyYWsAAABcdGtoZAAAAAMAAAAAAAAA" +
  "AAAAAAIAAAAAAAAIUAAAAAAAAAAAAAAAAQEAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAACRlZHRzAAAA" +
  "HGVsc3QAAAAAAAAAAQAAB9AAAAQAAAEAAAAAAfVtZGlhAAAAIG1kaGQAAAAAAAAAAAAAAAAAAB9AAABCgFXEAAAAAAAtaGRscgAAAAAAAAAAc291" +
  "bgAAAAAAAAAAAAAAAFNvdW5kSGFuZGxlcgAAAAGgbWluZgAAABBzbWhkAAAAAAAAAAAAAAAkZGluZgAAABxkcmVmAAAAAAAAAAEAAAAMdXJsIAAA" +
  "AAEAAAFkc3RibAAAAGpzdHNkAAAAAAAAAAEAAABabXA0YQAAAAAAAAABAAAAAAAAAAAAAgAQAAAAAB9AAAAAAAA2ZXNkcwAAAAADgICAJQACAASA" +
  "gIAXQBUAAAAAAB9AAAABPwWAgIAFFYhW5QAGgICAAQIAAAAgc3R0cwAAAAAAAAACAAAAEAAABAAAAAABAAACgAAAAChzdHNjAAAAAAAAAAIAAAAB" +
  "AAAAAQAAAAEAAAACAAAACAAAAAEAAABYc3RzegAAAAAAAAAAAAAAEQAAABUAAAAEAAAABAAAAAQAAAAEAAAABAAAAAQAAAAEAAAABAAAAAQAAAAE" +
  "AAAABAAAAAQAAAAEAAAABAAAAAQAAAAEAAAAHHN0Y28AAAAAAAAAAwAABcgAAAhmAAAIkQAAABpzZ3BkAQAAAHJvbGwAAAACAAAAAf//AAAAHHNi" +
  "Z3AAAAAAcm9sbAAAAAEAAAARAAAAAQAAAGJ1ZHRhAAAAWm1ldGEAAAAAAAAAIWhkbHIAAAAAAAAAAG1kaXJhcHBsAAAAAAAAAAAAAAAALWlsc3QA" +
  "AAAlqXRvbwAAAB1kYXRhAAAAAQAAAABMYXZmNTguMjguMTAxAAAACGZyZWUAAALxbWRhdN4CAExhdmM1OC41My4xMDAAAjBADgAAAnIGBf//btxF" +
  "6b3m2Ui3lizYINkj7u94MjY0IC0gY29yZSAxNTcgcjI5NzAgNTQ5M2JlOCAtIEguMjY0L01QRUctNCBBVkMgY29kZWMgLSBDb3B5bGVmdCAyMDAz" +
  "LTIwMTkgLSBodHRwOi8vd3d3LnZpZGVvbGFuLm9yZy94MjY0Lmh0bWwgLSBvcHRpb25zOiBjYWJhYz0wIHJlZj0zIGRlYmxvY2s9MTotMzotMyBh" +
  "bmFseXNlPTB4MToweDExMSBtZT1oZXggc3VibWU9NyBwc3k9MSBwc3lfcmQ9Mi4wMDowLjcwIG1peGVkX3JlZj0xIG1lX3JhbmdlPTE2IGNocm9t" +
  "YV9tZT0xIHRyZWxsaXM9MSA4eDhkY3Q9MCBjcW09MCBkZWFkem9uZT0yMSwxMSBmYXN0X3Bza2lwPTEgY2hyb21hX3FwX29mZnNldD0tNCB0aHJl" +
  "YWRzPTEgbG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0wIG5yPTAgZGVjaW1hdGU9MSBpbnRlcmxhY2VkPTAgYmx1cmF5X2NvbXBh" +
  "dD0wIGNvbnN0cmFpbmVkX2ludHJhPTAgYmZyYW1lcz0wIHdlaWdodHA9MCBrZXlpbnQ9MjUwIGtleWludF9taW49MSBzY2VuZWN1dD00MCBpbnRy" +
  "YV9yZWZyZXNoPTAgcmNfbG9va2FoZWFkPTQwIHJjPWNyZiBtYnRyZWU9MSBjcmY9MjMuMCBxY29tcD0wLjYwIHFwbWluPTAgcXBtYXg9NjkgcXBz" +
  "dGVwPTQgaXBfcmF0aW89MS40MCBhcT0xOjEuMjAAgAAAAA9liIQF85///w9FAAFXn4ABGCAHARggBwEYIAcBGCAHARggBwEYIAcBGCAHARggBwAA" +
  "AAdBmjgL5zqAARggBwEYIAcBGCAHARggBwEYIAcBGCAHARggBwEYIAc=";

let wanted = false, lock = null, asking = false, video = null;

function take() {
  if (!wanted || document.visibilityState !== "visible") return;
  if (navigator.wakeLock) {
    if (lock || asking) return;
    asking = true;
    navigator.wakeLock.request("screen").then((l) => {
      lock = l;
      lock.addEventListener("release", () => { lock = null; });
    }, () => playClip()).finally(() => { asking = false; }); // (refused - a power saver...: the video)
    return;
  }
  playClip();
}

function playClip() { // (called within a tap's handler: play() right away, no await before it - else not "from a tap")
  if (!video) {
    video = document.createElement("video");
    video.loop = true; video.playsInline = true;
    video.setAttribute("playsinline", ""); // (older Safaris read the attribute)
    video.src = CLIP;
    video.setAttribute("aria-hidden", "true");
    Object.assign(video.style, { position: "fixed", left: "-100px", top: "-100px", width: "1px", height: "1px",
      opacity: "0", pointerEvents: "none" });
    document.body.append(video);
  }
  if (video.paused) video.play().catch(() => {}); // (not from a tap yet: the next one)
}

export function initKeepAwake() {
  // Android, iOS (an iPad says it's a Mac: one with a touch screen)
  const ua = navigator.userAgent;
  wanted = /Android|iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
  if (!wanted) return;
  document.addEventListener("visibilitychange", take);
  document.addEventListener("pointerup", () => { if (!lock && (!video || video.paused)) take(); }, true);
  take();
}
