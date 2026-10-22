// Fetches the NightAgent call for the open ticket and hands it to render.js.
// The secret is a secure setting: Zendesk's proxy fills in {{setting.sidebar_secret}}, so it never reaches the browser.
(function () {
  var API = "https://nightshift-dispatch.vercel.app/api/zendesk/tickets/";
  var client = ZAFClient.init();
  var root = document.getElementById("app");

  function fit() {
    client.invoke("resize", { width: "100%", height: Math.min(document.body.scrollHeight + 8, 2000) + "px" });
  }

  function show(state) {
    NightAgentSidebar.render(root, state, load);
    fit();
  }

  function load() {
    show({ kind: "loading" });
    client.get("ticket.id").then(function (data) {
      var id = data["ticket.id"];
      if (!id) return show({ kind: "error", status: 0 });  // a ticket that isn't saved yet
      return client.request({
        url: API + encodeURIComponent(id),
        type: "GET",
        headers: { "X-Sidebar-Secret": "{{setting.sidebar_secret}}" },
        secure: true,
        cors: false,
        dataType: "json"
      }).then(function (call) {
        show({ kind: "call", call: call });
      }, function (err) {
        show({ kind: "error", status: (err && err.status) || 0 });
      });
    }).catch(function () {
      show({ kind: "error", status: 0 });
    });
  }

  client.on("app.registered", load);
  root.addEventListener("toggle", fit, true);  // the transcript opening or closing changes the height
})();
