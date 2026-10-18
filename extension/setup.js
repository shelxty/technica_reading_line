const msg = document.getElementById("msg");

document.getElementById("allow").addEventListener("click", async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    stream.getTracks().forEach((t) => t.stop()); // we only needed the permission
    await chrome.runtime.sendMessage({ target: "background", type: "start" });
    msg.className = "ok";
    msg.textContent = "Camera allowed and tracking started. You can close this tab and go to any page.";
  } catch (e) {
    msg.className = "err";
    msg.textContent =
      e.name === "NotAllowedError"
        ? "Camera was blocked. Click the camera icon in the address bar, allow it, then try again."
        : `Couldn't open the camera: ${e.message}`;
  }
});
