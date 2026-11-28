// Test setup: jsdom has no HTMLDialogElement.showModal / close, which the picker dialog uses
// (components/ProviderPicker.tsx). Minimal stand-ins: set or remove `open`, and fire `close`.
if (typeof HTMLDialogElement !== "undefined") {
  const proto = HTMLDialogElement.prototype;
  proto.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  proto.show = proto.showModal;
  proto.close = function close(this: HTMLDialogElement) {
    if (!this.hasAttribute("open")) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}
