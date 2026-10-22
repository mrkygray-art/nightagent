// Draws the sidebar from the NightAgent response. Server text only ever goes in through textContent,
// never innerHTML, so a transcript can't inject markup.
var NightAgentSidebar = (function () {
  // Same wording as the call report on the NightAgent board (app/report.py TOOL_NAMES)
  var TOOLS = {
    lookup_customer: "Looked up the account",
    create_ticket: "Created the ticket",
    page_on_call_tech: "Alerted the on-call technician",
    record_follow_up_outcome: "Saved the check-in result",
    take_message: "Took a message",
    billing_lookup: "Looked up the invoices",
    request_billing_review: "Opened a billing review",
    record_sales_interest: "Recorded the upgrade interest",
    check_ticket_status: "Checked an existing ticket",
    add_ticket_note: "Added a note to an existing ticket",
    transfer_to_agent: "Handed the call to a specialist"
  };
  var PRIORITY_CLASS = { emergency: "high", urgent: "medium", routine: "normal" };
  var STATUS_MARK = { pass: "✓", fail: "✗", pending: "…", na: "–", info: "i" };
  var STATUS_WORD = { pass: "Passed", fail: "Failed", pending: "Waiting", na: "Not applicable", info: "Info" };
  var ERRORS = {
    401: "The app's secret doesn't match NightAgent's. An admin can update it in the app's settings.",
    404: "No NightAgent call on this ticket. NightAgent only has details for tickets it made after a call.",
    429: "Too many requests just now. Try again in a minute.",
    503: "NightAgent's sidebar isn't switched on yet (no secret set on the server)."
  };

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function section(title, extra) {
    var box = el("section");
    var h = el("h2", null, title);
    if (extra) h.appendChild(el("span", "muted", " " + extra));
    box.appendChild(h);
    return box;
  }

  function clock(secs) {
    if (typeof secs !== "number") return "";
    var s = Math.max(0, Math.round(secs));
    return Math.floor(s / 60) + ":" + (s % 60 < 10 ? "0" : "") + (s % 60);
  }

  function when(tool) {
    if (tool.source === "elevenlabs") return clock(tool.seconds_into_call);
    var d = tool.called_at ? new Date(tool.called_at) : null;
    return d && !isNaN(d) ? d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" }) : "";
  }

  function header(call) {
    var box = el("header");
    var top = el("div", "row");
    top.appendChild(el("span", "pill " + (PRIORITY_CLASS[call.priority] || "normal"), call.priority_label || "Priority not set"));
    top.appendChild(el("span", "muted", call.nightagent_ticket_id));
    box.appendChild(top);
    box.appendChild(el("p", "caller", call.caller_name || "Caller didn't give a name"));
    if (call.board_status_label) {
      // The board's own stage; Zendesk changes only move it along the allowed steps (app/zendesk_sync.py)
      var synced = call.zendesk_assignee_name ? " · Assigned to " + call.zendesk_assignee_name : "";
      box.appendChild(el("p", "muted", "On the NightAgent board: " + call.board_status_label + synced));
    }
    return box;
  }

  function tools(list) {
    var failed = list.filter(function (t) { return !t.ok; }).length;
    var box = section("Tool calls", list.length ? "(" + list.length + (failed ? ", " + failed + " failed" : "") + ")" : "");
    if (!list.length) {
      box.appendChild(el("p", "note", "No tool calls recorded."));
      return box;
    }
    var ol = el("ol", "tools");
    list.forEach(function (t) {
      var li = el("li", t.ok ? "ok" : "failed");
      li.appendChild(el("span", "mark", t.ok ? "✓" : "✗"));
      var body = el("span", "body");
      body.appendChild(el("span", null, (TOOLS[t.name] || t.name.replace(/_/g, " ")) + (t.ok ? "" : " (failed)")));
      var meta = [t.name, t.agent && t.agent !== "Sam" ? t.agent : "", when(t)].filter(Boolean).join(" · ");
      body.appendChild(el("span", "meta", meta));
      li.appendChild(body);
      ol.appendChild(li);
    });
    box.appendChild(ol);
    if (list[0].source === "nightagent_log") {
      box.appendChild(el("p", "note", "From NightAgent's own log until ElevenLabs' analysis arrives; failed attempts show after that."));
    }
    return box;
  }

  function checks(check) {
    if (!check) return null;
    var score = check.score === null || check.score === undefined ? "" : check.score + "% · " + check.passed + " of " + check.applicable;
    var box = section("Call check", score);
    var ul = el("ul", "checks");
    check.checks.forEach(function (c) {
      var li = el("li", c.status);
      li.appendChild(el("span", "mark", STATUS_MARK[c.status] || "?")).setAttribute("aria-label", STATUS_WORD[c.status] || c.status);
      var body = el("span", "body");
      var title = el("span", null, c.label);
      if (c.judged_by === "ai") title.appendChild(el("span", "tag", "AI-judged"));
      body.appendChild(title);
      if (c.detail) body.appendChild(el("span", "meta", c.detail));
      li.appendChild(body);
      ul.appendChild(li);
    });
    box.appendChild(ul);
    return box;
  }

  function transcript(lines) {
    var box = el("details", "transcript");
    box.appendChild(el("summary", null, "Transcript (" + lines.length + " lines)"));
    if (!lines.length) box.appendChild(el("p", "note", "Not stored yet."));
    lines.forEach(function (line) {
      var p = el("p", line.speaker === "Caller" ? "caller-line" : "agent-line");
      p.appendChild(el("strong", null, line.speaker + ": "));
      p.appendChild(document.createTextNode(line.text));
      box.appendChild(p);
    });
    box.appendChild(el("p", "note", "Phone numbers are cut to the last four digits."));
    return box;
  }

  function refreshButton(onRefresh) {
    var b = el("button", "refresh", "Refresh");
    b.type = "button";
    b.addEventListener("click", onRefresh);
    return b;
  }

  function render(root, state, onRefresh) {
    root.textContent = "";
    if (state.kind === "loading") {
      root.appendChild(el("p", "note", "Loading the NightAgent call…"));
      return;
    }
    if (state.kind === "error") {
      root.appendChild(el("p", state.status === 404 ? "note" : "note error",
        ERRORS[state.status] || "Couldn't reach NightAgent. Check your connection and try again."));
      if (state.status !== 404) root.appendChild(refreshButton(onRefresh));
      return;
    }
    var call = state.call;
    root.appendChild(header(call));
    var summary = section("Call summary");
    summary.appendChild(el("p", null, call.call_summary || "No summary yet."));
    if (call.analysis_status !== "done") {
      summary.appendChild(el("p", "note", "ElevenLabs is still analyzing this call. Refresh in a minute."));
    }
    root.appendChild(summary);
    root.appendChild(tools(call.tool_calls || []));
    var c = checks(call.call_check);
    if (c) root.appendChild(c);
    root.appendChild(transcript(call.transcript || []));
    root.appendChild(refreshButton(onRefresh));
  }

  return { render: render, clock: clock };
})();
