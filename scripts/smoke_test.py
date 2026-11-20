# -*- coding: utf-8 -*-
"""前端冒烟测试：无头 Chrome 跑一组 DOM 断言，防止几何/渲染/交互回归。

覆盖：数据规模、技能表属性图标、魂印长文本封顶、属性口径开关（宽松／严格／chip）、
编辑器卡片尺寸与层级、添加技能卡后的连线端点与线型、便签作为连线端点、
连线颜色（设置／落库／恢复默认／图鉴回放）、技能连线备注落库、定位与备注（图鉴显示／编辑字段合并／筛选定位组／顶部备注开关）、技能表与重点技能候选倒序、双第五只标一条重点、重点只认编辑设置、神谕特训不自动算重点、图鉴线型与卡片尺寸、
删除后回库面板可重加（软删除与 `inListOf` 一致）、单体系导出载荷。
全部通过时退出码 0。

用法::

    python scripts/smoke_test.py            # 自动找 Chrome / Edge
    python scripts/smoke_test.py --browser "C:\\path\\to\\chrome.exe" --keep
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "references" / "spirit_synergy_view.html"
PROBE = r"""
<script>
(function(){
  var R = [];
  function ok(name, cond, extra){ R.push({name:name, pass:!!cond, extra:extra==null?"":String(extra)}); }
  // 任一步抛错时把错误当成一条失败断言交回去，否则整条链断掉、只报「未拿到结果」
  var step = function(fn, ms){ setTimeout(function(){
    try{ fn(); }
    catch(err){
      R.push({name:"脚本异常", pass:false, extra:String(err && err.stack || err).slice(0,160)});
      document.title = "SMOKE:" + JSON.stringify(R);
    }
  }, ms); };

  step(function(){
    // 218 是收录基准；库添加（DATA.library.adds）会在运行时补节点，所以用下限断言
    ok("数据规模", DATA.nodes.length>=218 && DATA.systems.length===21,
       DATA.nodes.length+" 只 / "+DATA.systems.length+" 体系");
    select("4586", false);
    step(function(){
      var hero = document.querySelector(".povl h2");
      var prop = document.querySelectorAll('.skilltable td.st img[src*="prop"]').length;
      ok("图鉴详情", hero && /空元行者/.test(hero.textContent), hero ? hero.textContent : "no-hero");
      ok("属性技能专属图标", prop > 0, "prop 图标 "+prop+" 个");

      // 定位与备注（2026-11-18）：定位分类与特色定位合并成「定位」，
      // 实战备注与核心机制合并成「备注」，两者都要在图鉴可见。
      select("2987", false);
      var dtags = document.querySelectorAll(".hero .dtag");
      var ownTags = document.querySelectorAll(".hero .dtag.own");
      ok("图鉴显示定位", dtags.length >= 2 && ownTags.length >= 1,
         dtags.length + " 个（自定义 " + ownTags.length + "）");
      var dnote = document.querySelector("#hero .dnote");
      ok("图鉴显示备注", !!dnote && dnote.textContent.trim().split("\n").length >= 2,
         dnote ? dnote.textContent.trim().split("\n").length + " 行" : "无备注");

      // 技能表倒序（2026-11-18）：重点仍前置，其余同档按源顺序倒序，末行应是源数据的第一条（最低学习等级）
      var ordNode = effective("2987") || nodeOf("2987") || {};
      var ordSrc = skillsOf(ordNode), ordRows = orderedSkills(ordNode);
      var lastCell = document.querySelector(".skilltable tbody tr:last-child td.nm");
      ok("技能表倒序", ordRows.length > 2 && ordRows[ordRows.length - 1].n === ordSrc[0].n &&
         !!lastCell && lastCell.textContent.indexOf(ordSrc[0].n) === 0,
         "末行 " + (lastCell ? lastCell.textContent.trim().slice(0, 12) : "-") +
         " / 源首 " + ordSrc[0].n);

      // 双第五精灵（2026-11-18）：第五即使带特训/神谕标记也不算重点，
      // 否则会出现两条「重点第五」。#3488 有 3 条第五、其中两条带 sp。
      select("3488", false);
      var fifKey = [].map.call(document.querySelectorAll(".skilltable tbody tr.key td.nm"),
        function(x){ return x.textContent.trim(); }).filter(function(t){ return /第五/.test(t); });
      ok("双第五只标一条重点", fifKey.length <= 1,
         fifKey.length + " 条" + (fifKey.length ? "：" + fifKey.join(" / ") : ""));
      // 重点只认编辑设置（key_skills）：神谕/特训/第五都不再自动算重点
      var keyCount3488 = document.querySelectorAll(".skilltable tbody tr.key").length;
      var set3488 = keySkillsOf(effective("3488") || nodeOf("3488") || {}).length;
      ok("重点只认编辑设置", keyCount3488 === set3488,
         keyCount3488 + " 条 / 设置 " + set3488);
      select("4186", false);
      var keyCount4186 = document.querySelectorAll(".skilltable tbody tr.key").length;
      var set4186 = keySkillsOf(effective("4186") || nodeOf("4186") || {}).length;
      ok("神谕特训不自动算重点", keyCount4186 === set4186,
         keyCount4186 + " 条 / 设置 " + set4186);
      select("2987", false);   // 恢复后续断言依赖的选中精灵

      // 顶部工具栏（2026-11-18）：管理体系改名、精选拉取换成备注开关（开＝蓝、关＝常规按钮）
      var nbtn = document.getElementById("btnNote");
      ok("顶部按钮已改名", document.getElementById("btnSys").textContent.trim() === "管理体系" &&
         !document.getElementById("btnPullPick"), "");
      ok("备注开关默认开", !!nbtn && nbtn.classList.contains("primary") &&
         nbtn.getAttribute("aria-pressed") === "true", nbtn ? nbtn.className : "missing");
      if(nbtn){
        nbtn.click();
        var noteOff = !document.querySelector("#hero .dnote") && !nbtn.classList.contains("primary");
        nbtn.click();
        ok("备注开关可关可开", noteOff && !!document.querySelector("#hero .dnote") &&
           nbtn.classList.contains("primary"), "关后无备注=" + noteOff);
      }

      openEditor();
      var elabels = [].map.call(document.querySelectorAll("#fields .fl"), function(x){ return x.textContent.trim(); });
      var staleLabel = elabels.filter(function(t){ return /定位分类|特色定位|实战备注|核心机制/.test(t); });
      ok("编辑字段已合并", elabels.indexOf("定位") >= 0 && elabels.indexOf("备注") >= 0 && !staleLabel.length,
         elabels.join(" / "));
      ok("定位有特色入口", !!document.querySelector("#fields .addown"), "");
      // 重点技能的候选菜单也要跟随倒序（此前仍用源顺序）
      var ksBox = document.querySelector('#fields .chipeditor[data-key="key_skills"]');
      if(ksBox) ksBox.querySelector(".addchip").click();
      var ksOpts = ksBox ? [].map.call(ksBox.querySelectorAll(".chipopt"), function(b){ return b.getAttribute("data-v"); }) : [];
      ok("重点技能候选也倒序", ksOpts.length > 2 && ksOpts[ksOpts.length - 1] === ordSrc[0].n,
         (ksOpts.length ? ksOpts[0] + " … " + ksOpts[ksOpts.length - 1] : "无选项"));
      closeEditor();

      openFilterPanel();
      var roleGroup = [].filter.call(document.querySelectorAll("#fBody .fgroup"), function(g){
        return /定位/.test(g.querySelector("h5").textContent); })[0];
      var roleOpts = roleGroup ? [].map.call(roleGroup.querySelectorAll(".fopt"), function(b){ return b.dataset.v; }) : [];
      var classKeys = Object.keys(TERMS.classes || {});
      ok("筛选有定位组", !!roleGroup && classKeys.every(function(k){ return roleOpts.indexOf(k) >= 0; }),
         roleOpts.length + " 个选项");
      closeFilterPanel();

      // 魂印长文本封顶（2026-11-17）：右列不再被撑高，超出改框内滚动
      select("4604", false);
      var sbox = document.querySelector(".hero .soul");
      ok("魂印长文本封顶", !!sbox && getComputedStyle(sbox).maxHeight !== "none" &&
         sbox.scrollHeight > sbox.clientHeight,
         sbox ? ("max=" + getComputedStyle(sbox).maxHeight + " 可视=" + sbox.clientHeight +
                 " 全文=" + sbox.scrollHeight) : "no .soul");
      var soulBtn = document.getElementById("soulToggle");
      ok("长魂印有展开入口", !!soulBtn && !soulBtn.hidden, soulBtn ? soulBtn.textContent : "missing");
      if(soulBtn && !soulBtn.hidden){
        soulBtn.click();
        var full = document.querySelector(".hero .soul");
        ok("展开后不再封顶", !!full && full.scrollHeight <= full.clientHeight + 4 &&
           document.getElementById("soulToggle").textContent === "收起",
           full ? ("可视=" + full.clientHeight + " 全文=" + full.scrollHeight) : "no .soul");
        document.getElementById("soulToggle").click();
      }
      select("4586", false);
      var shortBtn = document.getElementById("soulToggle");
      ok("短魂印不出现展开入口", !!shortBtn && shortBtn.hidden,
         shortBtn ? (shortBtn.hidden ? "hidden" : "visible") : "missing");

      // 属性口径开关（2026-11-17）：宽松＝含该属性的双属性也收；严格＝只要纯属性
      var pureAttr = attrParts(DATA.nodes[0].attr)[0];
      var oneWant = new Set([pureAttr]);
      var dualAttr = (DATA.nodes || []).map(function(n){ return n.attr; }).find(function(a){
        var ps = attrParts(a); return ps.length === 2 && ps.indexOf(pureAttr) >= 0;
      });
      attrStrict = false;
      var lenPure = attrFilterHit(pureAttr, oneWant);
      var lenDual = dualAttr ? attrFilterHit(dualAttr, oneWant) : false;
      attrStrict = true;
      var strPure = attrFilterHit(pureAttr, oneWant);
      var strDual = dualAttr ? attrFilterHit(dualAttr, oneWant) : true;
      ok("属性口径-宽松", lenPure && lenDual,
         "纯=" + lenPure + " 双=" + lenDual + "（" + (dualAttr || "无双属性样本") + "）");
      ok("属性口径-严格", strPure && !strDual, "纯=" + strPure + " 双=" + strDual);

      openFilterPanel();
      var swRow = document.querySelector('#fBody [data-sw="attrStrict"]');
      var swBtn = swRow && swRow.querySelector(".attrsw");
      ok("属性开关渲染", !!swBtn && swBtn.getAttribute("aria-checked") === "true",
         swBtn ? "aria-checked=" + swBtn.getAttribute("aria-checked") : "missing");
      if(swBtn) swBtn.click();
      ok("属性开关可关闭", attrStrict === false, "attrStrict=" + attrStrict);
      FILTER.attr.add(pureAttr); applyFilter();
      ok("宽松模式无口径 chip", !document.querySelector('#fChips .fchip[data-g="attrStrict"]'), "");
      attrStrict = true; applyFilter();
      ok("严格模式带口径 chip", !!document.querySelector('#fChips .fchip[data-g="attrStrict"]'),
         document.querySelector("#fChips").textContent.trim());
      FILTER.attr.clear(); attrStrict = false; applyFilter(); closeFilterPanel();

      openSystemManager("edit", "涂蝶体系");
      step(function(){
        var cn = document.querySelectorAll("#sysNodes .cnode");
        ok("编辑器成员", cn.length===4, cn.length+" 张卡");
        var zNode = cn[0] ? getComputedStyle(cn[0]).zIndex : "-";
        ok("精灵卡层级", zNode==="5", "z="+zNode);

        var pet = document.querySelector("#sysNodes .cnode");
        openSkillPicker(pet.getAttribute("data-id"));
        step(function(){
          var rows = document.querySelectorAll("#skillList .spick");
          if(rows[0]) rows[0].click();
          step(function(){
            var sk = document.querySelector("#sysSkills .skcard");
            var w = sk ? Math.round(sk.offsetWidth) : 0, h = sk ? Math.round(sk.offsetHeight) : 0;
            ok("技能卡尺寸", w===GEO.skW && h===GEO.skH, w+"x"+h+" vs "+GEO.skW+"x"+GEO.skH);
            var lines = document.querySelectorAll("#sysLinks line.clink.own");
            // 体系文件可能自带技能卡（如涂蝶体系的「蓝染」），第一条黄线未必是刚加的那条。
            // 只按新技能卡的归属精灵找线，且端点方向允许正反两种，避免依赖 nodes/skills 顺序。
            var s = graph.skills[graph.skills.length-1];
            var p = s && graph.nodes.find(function(n){ return String(n.id)===String(s.pet); });
            var w = s ? (s.w||GEO.skW) : 0, h = s ? (s.h||GEO.skH) : 0;
            var ep = p ? [p.x+GEO.editCx, p.y+GEO.editCy] : [];
            var es = s ? [(Number(s.x)||0)+w/2, (Number(s.y)||0)+h/2] : [];
            var near = function(a,b){ return Math.abs(a[0]-b[0])<0.6 && Math.abs(a[1]-b[1])<0.6; };
            // 端点不再落在卡心，而是按 edgeSegment() 内缩（与图鉴同一份实现）
            var seg = (p && s) ? edgeSegment({x:ep[0],y:ep[1],w:GEO.editW,h:GEO.editH},
                                             {x:es[0],y:es[1],w:w,h:h}) : null;
            var e1 = seg ? [seg.sx, seg.sy] : [], e2 = seg ? [seg.ex, seg.ey] : [];
            var same = !!seg && Array.prototype.some.call(lines, function(L){
              var g=[[Number(L.getAttribute("x1")),Number(L.getAttribute("y1"))],
                     [Number(L.getAttribute("x2")),Number(L.getAttribute("y2"))]];
              return (near(g[0],e1)&&near(g[1],e2)) || (near(g[0],e2)&&near(g[1],e1));
            });
            var got = lines.length ? [lines[0].getAttribute("x1"),lines[0].getAttribute("y1"),
                                      lines[0].getAttribute("x2"),lines[0].getAttribute("y2")].join(",") : "no-line";
            ok("连线端点内缩一致", same, got+" / 期望 "+e1.map(function(v){return Math.round(v);}).join(",")+
               "→"+e2.map(function(v){return Math.round(v);}).join(","));
            // viewBox 与 SVG 尺寸必须 1:1（2026-11-17）：线端屏幕位置 = 自身坐标 × 画布缩放。
            // 一旦 viewBox 与元素尺寸不等，浏览器会整层缩放，线就跟卡片错位。
            var svgEl = document.getElementById("sysLinks");
            var svgR = svgEl.getBoundingClientRect();
            var kScale = svgR.width / Number(svgEl.getAttribute("width"));
            var l1 = document.querySelector("#sysLinks line.clink");
            var l1r = l1.getBoundingClientRect();
            var dx = Math.abs((l1r.left - svgR.left) - Number(l1.getAttribute("x1")) * kScale);
            var dy = Math.abs((l1r.top - svgR.top) - Number(l1.getAttribute("y1")) * kScale);
            ok("连线与画布坐标 1:1", dx < 2 && dy < 2,
               "dx=" + dx.toFixed(1) + " dy=" + dy.toFixed(1) + " scale=" + kScale.toFixed(3));

            // 线型与图鉴一致（2026-11-17）：技能卡线是短虚线，不再画成实线
            var skLine = document.querySelector("#sysLinks line.clink.sk");
            var skDash = skLine ? getComputedStyle(skLine).strokeDasharray : "none";
            ok("技能线在编辑器里是虚线", !!skLine && skDash !== "none", skLine ? skDash : "无 sk 线");

            // 便签也能当连线端点（2026-11-17）：精灵 → 便签，线端须落在便签实测中心
            var p0 = graph.nodes[0];
            graph.notes = graph.notes || [];
            graph.notes.push({id:"nsmoke", x:320, y:60, text:"冒烟便签"});
            drawGraph();
            addEdge(p0.id, "nsmoke");
            var nt = graph.notes[graph.notes.length-1];
            var nc = [(Number(nt.x)||0)+((nt.w||GEO.noteW)/2), (Number(nt.y)||0)+((nt.h||GEO.noteH)/2)];
            var nearN = function(a,b){ return Math.abs(a[0]-b[0])<0.6 && Math.abs(a[1]-b[1])<0.6; };
            var pc = [p0.x+GEO.editCx, p0.y+GEO.editCy];
            var nseg = edgeSegment({x:pc[0],y:pc[1],w:GEO.editW,h:GEO.editH},
                                   {x:nc[0],y:nc[1],w:(nt.w||GEO.noteW),h:(nt.h||GEO.noteH)});
            var nExpected = [[nseg.sx,nseg.sy],[nseg.ex,nseg.ey]];
            var noteHit = Array.prototype.some.call(document.querySelectorAll("#sysLinks line.clink"), function(L){
              var g=[[Number(L.getAttribute("x1")),Number(L.getAttribute("y1"))],
                     [Number(L.getAttribute("x2")),Number(L.getAttribute("y2"))]];
              return Array.prototype.some.call(nExpected, function(pt){
                return nearN(g[0],pt) || nearN(g[1],pt); });
            });
            ok("便签可连线", noteHit && graph.edges.some(function(e){
              return String(e.a)==="nsmoke" || String(e.b)==="nsmoke"; }),
              "便签中心 "+nc.map(Math.round).join(","));
            // 短便签不被最小宽度撑开（旧 min-width:110px 会让「二选一」这种短文本右边空一大截）
            var ntBox = document.querySelector('.cnote[data-id="nsmoke"]');
            var ntW = ntBox ? Math.round(ntBox.offsetWidth) : -1;
            ok("短便签贴合文本", ntW > 0 && ntW < 90, ntW + "px / 文本 4 字");

            var ntLine = document.querySelector("#sysLinks line.clink.nt");
            ok("便签线在编辑器里是点线", !!ntLine &&
               getComputedStyle(ntLine).strokeDasharray !== "none",
               ntLine ? getComputedStyle(ntLine).strokeDasharray : "无 nt 线");

            // 连线颜色（2026-11-17）：右键线→「设置线条颜色」，选中即生效并写入 canvas.edge_colors
            openEdgeColor(0, 40, 40);
            ok("取色面板打开", !document.getElementById("edgeColor").hidden &&
               document.querySelectorAll("#edgeColorGrid button").length === EDGE_PALETTE.length,
               document.querySelectorAll("#edgeColorGrid button").length + " 个色块");
            setEdgeColor("#ef4444");
            var l0 = document.querySelector('#sysLinks line.clink[data-i="0"]');
            var ec0 = l0 ? getComputedStyle(l0).getPropertyValue("--ec").trim() : "";
            ok("连线颜色生效", !!l0 && ec0 === "#ef4444", l0 ? ("--ec=" + ec0) : "no line");

            var payload = sysExportPayload();
            var nl = (payload && payload.canvas && payload.canvas.note_links ? payload.canvas.note_links : [])
              .filter(function(l){ return String(l.a)==="nsmoke" || String(l.b)==="nsmoke"; });
            ok("便签连线落库", nl.length===1, JSON.stringify(nl[0]||null));

            var e0 = graph.edges[0], ekey = edgeKeyOf(e0.a, e0.b);
            var savedColors = (payload && payload.canvas && payload.canvas.edge_colors) || {};
            ok("连线颜色落库", savedColors[ekey] === "#ef4444", JSON.stringify(savedColors));

            openEdgeColor(0, 40, 40); setEdgeColor("");
            var l0b = document.querySelector('#sysLinks line.clink[data-i="0"]');
            var ecb = l0b ? getComputedStyle(l0b).getPropertyValue("--ec").trim() : "?";
            ok("恢复默认线色", !!l0b && ecb === "",
               l0b ? (ecb === "" ? "(无 --ec，跟随主题)" : "--ec=" + ecb) : "no line");

            // 技能卡/备注文本连线的备注要能落库：以前只存两端 key，备注保存后丢失
            var skE = graph.edges.find(function(e){ return isSkillKey(e.a) || isSkillKey(e.b); });
            if(skE) skE.note = "冒烟技能备注";
            var pNotes = (sysExportPayload().canvas || {}).link_notes || {};
            var hitNotes = Object.keys(pNotes).filter(function(k){ return pNotes[k] === "冒烟技能备注"; });
            ok("技能连线备注落库", hitNotes.length === 1, JSON.stringify(pNotes));

            var na = graph.nodes[0].id, nb2 = graph.nodes[1].id;
            var gv = graphView([na, nb2], [{a:na, b:nb2, note:""}],
              {nodes:[], notes:[], edge_colors:(function(){ var m={}; m[edgeKeyOf(na, nb2)] = "#3b82f6"; return m; })()}, "t");
            ok("图鉴回放线色", gv.indexOf("--ec:#3b82f6") >= 0,
               gv.indexOf("--ec") >= 0 ? "命中 --ec" : "无 --ec");
            ok("体系文件导出", payload && payload.$schema==="seer-system/1" && payload.key==="涂蝶体系",
               payload ? (payload.$schema+" "+payload.key) : "null");

            closeSystemManager();
            step(function(){
              select("4800", false);
              step(function(){
                var g = document.querySelector("#systemsView .gnode");
                var z = g ? getComputedStyle(document.querySelector("#systemsView .ginner")).zoom : 1;
                var gw = g ? Math.round(g.getBoundingClientRect().width / z) : 0;
                var gh = g ? Math.round(g.getBoundingClientRect().height / z) : 0;
                ok("图鉴卡片尺寸", gw===GEO.nodeW && gh===GEO.nodeH, gw+"x"+gh);
                ok("图鉴渲染", document.querySelectorAll("#systemsView .gseg").length>0,
                   document.querySelectorAll("#systemsView .gseg").length+" 个体系画布");
                var gsk = document.querySelectorAll("#systemsView line.gskill");
                ok("图鉴技能线虚线", gsk.length>0 &&
                   getComputedStyle(gsk[0]).strokeDasharray !== "none",
                   gsk.length+" 条，dash="+(gsk[0]?getComputedStyle(gsk[0]).strokeDasharray:"-"));
                // 库内技能补齐（2026-11-18）：「无限自由」等 4 只在 media 层之外，
                // 原来 skills 为空、点进去技能表显示「未取回技能数据」。
                var libX = LIB_MAP.get(3383) || {};
                ok("库内技能已补", (libX.skills || []).length >= 17,
                   (libX.skills || []).length + " 条 / " + (libX.name || "-"));
                addFromLibrary(3383); select("3383", false);
                step(function(){
                  var tbl = document.querySelector(".skilltable");
                  var rows = tbl ? tbl.querySelectorAll("tbody tr").length : 0;
                  ok("补入后技能表可渲染", rows > 0 && rows === (libX.skills || []).length,
                     rows + " 行");

                  // 删除后回库重加（2026-11-19）：删除是软删除，节点仍在 DATA.nodes，
                  // 库面板以前用 nodeOf() 判「已添加」，导致删掉的精灵永远显示「已添加」且加不回来。
                  var DK = "3383";
                  markDeleted(DK, true);
                  renderAll();
                  var gone = !filtered().some(function(n){ return String(n.id) === DK; });
                  openLibrary();
                  $("libQ").value = "无限自由";
                  renderLibraryResults(true);
                  var rb = document.querySelector('#libResults .lrow[data-id="3383"] button[data-add]');
                  ok("删除后库面板可重加",
                     gone && !!rb && rb.textContent.trim() === "添加" && !rb.disabled,
                     (gone ? "已离开列表" : "仍在列表") + "；按钮=" +
                     (rb ? rb.textContent.trim() + (rb.disabled ? "(禁用)" : "") : "无"));
                  if(rb && !rb.disabled) addFromLibrary(DK);
                  step(function(){
                    var back = filtered().some(function(n){ return String(n.id) === DK; });
                    ok("重加后回到列表", back && !isDeleted(DK), back ? "已恢复" : "未恢复");

                    // 魂印只显示最新一版（2026-11-20 用户口径：删掉「强化前／强化后」开关）
                    // 4186 资料层有 [旧, 新] 两版：图鉴必须只渲染新版、且没有任何切换控件
                    select("4186", false);
                    var soulBox = document.querySelector("#hero .soul");
                    var soulTxt = soulBox ? soulBox.textContent : "";
                    var verCtrl = document.querySelectorAll(
                      "#hero .soulver, #hero [data-soulver], #hero .soulver-chip, #hero .soultext").length;
                    ok("魂印只显示最新版",
                       /金祖之龍/.test(soulTxt) && !/250点护盾/.test(soulTxt),
                       soulTxt.slice(0, 14));
                    ok("魂印无版本切换控件", verCtrl === 0, verCtrl + " 个控件");

                    // 名词释义照旧按这唯一一版渲染（3711 当前版命中 3 个通用效果名词）
                    select("3711", false);
                    var tn = [].map.call(document.querySelectorAll("#termSlot .trow"),
                      function(el){ return el.dataset.term; }).join(",");
                    ok("魂印名词释义正常", !!tn, tn || "无");

                    document.title = "SMOKE:" + JSON.stringify(R);
                  }, 320);
                }, 420);
              }, 320);
            }, 200);
          }, 220);
        }, 200);
      }, 260);
    }, 260);
  }, 120);
})();
</script>
"""


def find_browser(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p
        raise SystemExit(f"找不到浏览器：{explicit}")
    env = os.environ.get("SMOKE_BROWSER")
    if env and Path(env).exists():
        return Path(env)
    for cand in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
    ):
        if Path(cand).exists():
            return Path(cand)
    raise SystemExit("没有可用的 Chrome/Edge，可用 --browser 指定路径")


def main() -> int:
    ap = argparse.ArgumentParser(description="前端冒烟测试（无头浏览器 + DOM 断言）")
    ap.add_argument("--browser", default=None, help="浏览器可执行文件路径")
    ap.add_argument("--keep", action="store_true", help="保留临时探针页面")
    args = ap.parse_args()

    if not HTML.exists():
        raise SystemExit(f"找不到前端产物：{HTML}（先跑 rebuild_view.py）")
    browser = find_browser(args.browser)

    html = HTML.read_text(encoding="utf-8")
    # 固定浅色主题，避免跟随系统导致截图/断言抖动
    seed = "<script>try{localStorage.setItem('seer_peak_view_theme','light');}catch(e){}</script>"
    html = html.replace('<meta charset="utf-8">', '<meta charset="utf-8">\r\n' + seed, 1)
    probe = HTML.parent / "_smoke_probe.html"      # 必须放在 references/ 下，相对资源才解析得到
    probe.write_text(html.replace("</body>", PROBE + "\r\n</body>", 1), encoding="utf-8")

    profile = Path(tempfile.mkdtemp(prefix="smoke-"))
    try:
        cmd = [str(browser), "--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--window-size=1500,1400", "--virtual-time-budget=15000",
               f"--user-data-dir={profile}", "--dump-dom", probe.as_uri()]
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=120).stdout
    finally:
        if not args.keep:
            probe.unlink(missing_ok=True)
        shutil.rmtree(profile, ignore_errors=True)

    m = re.search(r"<title>SMOKE:(\[.*?\])</title>", out, re.S)
    if not m:
        print("SMOKE 未拿到结果（页面可能报错）")
        if args.keep:
            print("探针页面保留在", probe)
        return 2
    try:
        results = json.loads(m.group(1).replace("&quot;", '"'))
    except json.JSONDecodeError:
        print("结果解析失败：", m.group(1)[:200])
        return 2

    failed = [r for r in results if not r["pass"]]
    for r in results:
        print(("PASS " if r["pass"] else "FAIL ") + r["name"] + (("  ← " + r["extra"]) if r["extra"] else ""))
    print(f"\n{len(results) - len(failed)}/{len(results)} 通过")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
