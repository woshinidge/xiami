# Auto-generated from Website/droprate.html
from __future__ import annotations

EMBEDDED_DROPRATE_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<link rel="icon" href="./222.ico" type="image/x-icon"/><link rel="shortcut icon" href="./222.ico" type="image/x-icon"/>
<title>默认站点 - 爆率查询</title>
<style>

        :root{--bg:#120706;--panel:#1f0f0d;--panel-soft:#2a1713;--text:#f8ecd2;--muted:#cbb58d;--line:rgba(255,220,165,.12);--line-strong:rgba(224,174,73,.42);--acc:#d7a23f;--acc-hover:#f7d694;--bad:#ff6b6b;--shadow:0 18px 48px rgba(0,0,0,.38);--shadow-soft:0 12px 28px rgba(0,0,0,.26);--focus:0 0 0 3px rgba(224,174,73,.24);}
        *{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;min-height:100vh;background:radial-gradient(circle at 50% 0,rgba(215,162,63,.16),transparent 24%),radial-gradient(circle at 18% 12%,rgba(121,34,23,.26),transparent 30%),linear-gradient(180deg,#1a0a08 0,#090403 54%,#040202 100%);color:var(--text);font-family:"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;line-height:1.6;text-rendering:optimizeLegibility}

        a{color:var(--acc);text-decoration:none;transition:color .2s ease,transform .2s ease,border-color .2s ease,background .2s ease,box-shadow .2s ease}a:hover{color:var(--acc-hover)}
        a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{outline:none;box-shadow:var(--focus)}
        .wrap{width:min(1200px,calc(100% - 32px));margin:0 auto}

        
        /* Header */
        .header{position:sticky;top:0;z-index:20;background:rgba(18,7,6,.88);border-bottom:1px solid var(--line-strong);box-shadow:0 10px 30px rgba(0,0,0,.28);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}

        .header .inner{display:flex;align-items:center;justify-content:space-between;gap:18px;width:min(1200px,calc(100% - 32px));margin:0 auto;padding:16px 0}
        .brand h1{margin:0;font-size:clamp(24px,3vw,30px);color:var(--acc);text-shadow:0 2px 8px rgba(0,0,0,.45);font-weight:800}
        .brand .sub{color:var(--muted);font-size:14px;margin-top:4px}
        .nav{display:flex;gap:18px;flex-wrap:wrap}
        .nav a{display:inline-flex;align-items:center;min-height:40px;font-size:15px;font-weight:700;padding:6px 0;position:relative}
        .nav a.active{color:var(--acc-hover)}
        .nav a::after{content:'';position:absolute;bottom:0;left:0;width:0;height:2px;border-radius:999px;background:var(--acc);transition:width .22s ease}
        .nav a:hover::after,.nav a.active::after{width:100%}


        /* Hero */
        .hero{background:linear-gradient(rgba(0,0,0,0.7),rgba(0,0,0,0.7)), url('./assets/bg.jpg');background-size:cover;padding:80px 0;text-align:center;border-bottom:1px solid var(--line)}
        .hero h2{font-size:48px;margin:0 0 20px;color:#fff;text-shadow:0 4px 10px #000}
        .hero p{font-size:18px;color:#ccc;max-width:800px;margin:0 auto 40px}
        .hero-media{margin:40px auto 0;max-width:980px}
        .hero-media iframe{width:100%;aspect-ratio:16/9;border:0;border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.6)}
        .hero-media video{width:100%;aspect-ratio:16/9;border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.6);background:#000}
        .btn-dl{display:inline-block;padding:16px 48px;background:var(--acc);color:#000;font-size:20px;font-weight:bold;border-radius:4px;box-shadow:0 0 20px rgba(212,175,55,0.4);transition:all .3s}
        .btn-dl:hover{transform:scale(1.05);background:var(--acc-hover);box-shadow:0 0 30px rgba(212,175,55,0.6);text-decoration:none;color:#000}

        /* Section */
        .section{padding:60px 0}
        .sec-title{text-align:center;margin-bottom:50px;position:relative}
        .sec-title h3{font-size:32px;color:var(--acc);margin:0;display:inline-block;padding:0 20px;background:var(--bg);position:relative;z-index:1}
        .sec-title::after{content:'';position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:200px;height:1px;background:var(--line);z-index:0}

        /* Versions */
        .v-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:30px}
        .v-card{background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden;transition:transform .3s,box-shadow .3s}
        .v-card:hover{transform:translateY(-5px);box-shadow:0 10px 30px rgba(0,0,0,.5);border-color:var(--acc)}
        .v-img{aspect-ratio:16/9;min-height:220px;background:radial-gradient(circle at 20% 20%,rgba(212,175,55,.16),transparent 55%),#050509;overflow:hidden;position:relative}
        .v-book{position:absolute;inset:0;perspective:1200px;transform-style:preserve-3d}
        .v-page{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#000;user-select:none;-webkit-user-select:none;pointer-events:none;backface-visibility:hidden;transform-style:preserve-3d}
        .v-page.v-back{visibility:hidden}
        .v-img.animating .v-page.v-back{visibility:visible}
        .v-img.flip-next .v-page.v-front{transform-origin:center center;animation:vFlipFrontNext .78s cubic-bezier(.2,.6,.2,1) both}
        .v-img.flip-next .v-page.v-back{transform-origin:center center;animation:vFlipBackNext .78s cubic-bezier(.2,.6,.2,1) both}
        .v-img.flip-prev .v-page.v-front{transform-origin:center center;animation:vFlipFrontPrev .78s cubic-bezier(.2,.6,.2,1) both}
        .v-img.flip-prev .v-page.v-back{transform-origin:center center;animation:vFlipBackPrev .78s cubic-bezier(.2,.6,.2,1) both}
        @keyframes vFlipFrontNext{from{transform:rotateY(0deg)}to{transform:rotateY(-180deg)}}
        @keyframes vFlipBackNext{from{transform:rotateY(180deg)}to{transform:rotateY(0deg)}}
        @keyframes vFlipFrontPrev{from{transform:rotateY(0deg)}to{transform:rotateY(180deg)}}
        @keyframes vFlipBackPrev{from{transform:rotateY(-180deg)}to{transform:rotateY(0deg)}}
        @media (prefers-reduced-motion:reduce){.v-img.flip-next .v-page,.v-img.flip-prev .v-page{animation:none}}
        .v-track{position:absolute;inset:0;display:flex;transform:translateX(0);transition:transform .55s ease;will-change:transform}
        .v-track img{width:100%;height:100%;flex:0 0 100%;object-fit:contain;background:#000;user-select:none;-webkit-user-select:none;pointer-events:none}
        .v-controls{position:absolute;inset:0;z-index:2}
        .v-arrow{pointer-events:auto;position:absolute;top:50%;transform:translateY(-50%);width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.45);border:1px solid rgba(255,255,255,.16);color:#fff;font-size:22px;line-height:1;cursor:pointer;opacity:.9;transition:opacity .15s ease,transform .15s ease,border-color .15s ease}
        .v-arrow:hover{opacity:1;border-color:rgba(212,175,55,.75);transform:translateY(-50%) scale(1.04)}
        .v-arrow.prev{left:10px}
        .v-arrow.next{right:10px}
        .v-dots{position:absolute;left:50%;bottom:10px;transform:translateX(-50%);display:flex;gap:6px;z-index:3}
        .v-dot{width:6px;height:6px;border-radius:50%;background:rgba(255,255,255,.22);transition:background .2s}
        .v-dot.active{background:var(--acc)}
        @media (prefers-reduced-motion:reduce){.v-track{transition:none}}
        .v-img .ph{position:absolute;top:0;left:0;width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:#333;font-size:48px}
        .v-card:hover .v-img img{filter:brightness(1.03)}
        .v-body{padding:24px}
        .v-title{font-size:20px;color:var(--acc);margin:0 0 12px;font-weight:bold}
        .v-desc{color:#ccc;font-size:14px;line-height:1.6;white-space:pre-wrap}

        /* Penguin */
        .penguin-fab{position:fixed;right:18px;bottom:18px;width:58px;height:58px;border-radius:50%;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.55);border:1px solid rgba(212,175,55,.75);box-shadow:0 10px 25px rgba(0,0,0,.5);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);z-index:9999;transition:transform .15s ease,background .15s ease,border-color .15s ease}
        .penguin-fab:hover{transform:translateY(-2px);background:rgba(0,0,0,.72);border-color:var(--acc-hover)}
        .penguin-fab svg{width:34px;height:34px}
        .penguin-inline{position:absolute;left:16px;top:16px;display:none;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;background:rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.14);color:var(--acc);font-size:12px;line-height:1;box-shadow:0 8px 18px rgba(0,0,0,.35)}
        .penguin-inline:hover{border-color:rgba(212,175,55,.75);color:var(--acc-hover)}
        .penguin-inline svg{width:14px;height:14px}

        /* Notice & Info */
        .info-grid{display:grid;grid-template-columns:2fr 1fr;gap:30px}
        .panel{background:var(--panel);border:1px solid var(--line);padding:24px;border-radius:8px}
        .panel-h{font-size:18px;color:var(--acc);margin:0 0 20px;padding-bottom:12px;border-bottom:1px solid var(--line)}
        .notice-list{list-style:none;padding:0;margin:0}
        .notice-list li{padding:10px 0;border-bottom:1px dashed var(--line);color:#ccc}
        .notice-list li:last-child{border:0}
        .qq-box{text-align:center;padding:20px;position:relative}
        .qq-num{font-size:24px;color:var(--acc);font-weight:bold;margin:10px 0;font-family:monospace}

        /* Footer */
        .footer{background:#000;padding:40px 0;text-align:center;color:#666;font-size:14px;margin-top:60px;border-top:1px solid var(--line)}
        
        /* Utils */
        .mono{font-family:Consolas,monospace}
        .muted{color:var(--muted)}
        
:root{--drop-radius:14px;}
.app{max-width:1200px;margin:20px auto 44px;background:linear-gradient(180deg,rgba(42,22,18,.96),rgba(18,8,8,.98));border-radius:18px;box-shadow:var(--shadow);overflow:hidden;border:1px solid var(--line)}

.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:14px 16px;background:rgba(30,12,10,.92);border-bottom:1px solid var(--line-strong);color:var(--text)}

.brand2{display:flex;align-items:center;gap:10px;font-weight:800;min-width:0}
.logoDot{width:34px;height:34px;border-radius:10px;background:rgba(109,31,22,.4);border:1px solid rgba(212,175,55,.45);display:flex;align-items:center;justify-content:center;font-size:14px;color:var(--acc-hover);flex:0 0 auto}

.nav2{display:flex;gap:8px;flex-wrap:wrap}
.navBtn{border:1px solid transparent;background:transparent;color:var(--text);padding:9px 12px;border-radius:10px;font-weight:800;cursor:pointer;transition:all .15s;min-height:40px;display:inline-flex;align-items:center;justify-content:center}
.navBtn:hover{background:rgba(212,175,55,.10);border-color:rgba(212,175,55,.25)}
.navBtn.active{background:linear-gradient(180deg,rgba(109,31,22,.92),rgba(57,18,14,.92));border-color:rgba(212,175,55,.55);color:var(--acc-hover)}
.navBtn.disabled{opacity:.5;cursor:not-allowed;pointer-events:none}
.rightBox{display:flex;align-items:center;gap:10px;flex-wrap:wrap;justify-content:flex-end}
.sel{border:1px solid var(--line);background:rgba(8,11,16,.58);color:var(--text);padding:10px 12px;border-radius:10px;outline:none;min-height:42px}
.sel option{color:#111}
.pill{padding:8px 12px;border-radius:999px;background:rgba(109,31,22,.36);border:1px solid rgba(212,175,55,.35);font-weight:800;color:var(--acc-hover);min-height:40px;display:inline-flex;align-items:center}

.toolbar{padding:12px 16px;background:rgba(24,10,8,.78);border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:center;flex-wrap:wrap;backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px)}

.search{flex:1;min-width:280px;display:flex;gap:10px;align-items:center}
.search input{flex:1;border:1px solid var(--line);background:#0b0f17;color:#fff;border-radius:10px;padding:10px 12px;outline:none;min-height:42px}
.search input::placeholder{color:#667085}
.search .mini{min-width:180px}
.modeWrap{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.modeBtn{border:1px solid var(--line);background:#0b0f17;color:#fff;padding:9px 12px;border-radius:10px;font-weight:900;cursor:pointer;min-height:42px}
.modeBtn:hover{border-color:rgba(212,175,55,.55);color:var(--acc-hover)}
.modeBtn.active{background:var(--acc);border-color:var(--acc);color:#000}
.toolRight{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.check{display:flex;align-items:center;gap:6px;color:#d7dae1;font-size:13px;min-height:40px}
.check input{transform:translateY(1px)}
.btn{border:1px solid var(--line);background:#150706;border-radius:10px;padding:9px 12px;cursor:pointer;font-weight:800;text-decoration:none;color:#fff;display:inline-flex;align-items:center;justify-content:center;min-height:42px;transition:all .15s}

.btn:hover{border-color:rgba(212,175,55,.55)}
.btn.primary{background:var(--acc);color:#000;border-color:var(--acc)}
.btn.primary:hover{background:var(--acc-hover);border-color:var(--acc-hover);color:#000}
.btn.ghost{background:transparent;color:var(--acc);border-color:rgba(212,175,55,.55)}
.content{padding:16px 16px 20px}

:root{--drop-col-height:clamp(420px,calc(100vh - 280px),760px);--drop-col-height-mobile:min(62vh,560px)}
.grid4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;align-items:stretch;grid-auto-rows:var(--drop-col-height)}
@media (max-width:1280px){.grid4{grid-template-columns:repeat(2,minmax(0,1fr))}}


@media (max-width:760px){
  .app{margin:0 auto 24px;border-radius:0;max-width:none}
  .grid4{grid-template-columns:1fr;gap:12px;grid-auto-rows:var(--drop-col-height-mobile)}

  .topbar{flex-direction:column;align-items:stretch}
  .nav2{flex-wrap:nowrap;overflow-x:auto;-webkit-overflow-scrolling:touch;padding-bottom:4px}
  .navBtn{white-space:nowrap;flex:0 0 auto}
  .rightBox{width:100%;justify-content:space-between}
  .rightBox > *{flex:1 1 auto}
  .search{min-width:0;flex-wrap:wrap}
  .search .mini{min-width:140px;flex:1}
  .modeWrap,.toolRight{width:100%;justify-content:space-between}
  .toolRight .btn,.toolRight .check{flex:1 1 auto}
  .content{padding:12px 12px 18px}
  .card{width:100%}
}
.col{position:relative;background:linear-gradient(180deg,rgba(42,22,18,.92),rgba(20,9,8,.98));border:1px solid var(--line);border-radius:14px;overflow:hidden;display:flex;flex-direction:column;min-height:0;min-width:0;height:100%;max-height:var(--drop-col-height);box-shadow:var(--shadow-soft);contain:layout paint}
@media (max-width:760px){.col{max-height:var(--drop-col-height-mobile)}}



.colH{position:sticky;top:0;z-index:3;padding:12px;background:linear-gradient(180deg,rgba(27,12,10,.98),rgba(17,8,7,.95));backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);color:var(--acc);display:flex;flex-direction:column;align-items:stretch;gap:10px;font-weight:900;border-bottom:1px solid var(--line);box-shadow:0 8px 18px rgba(0,0,0,.18)}

.colTitle{display:flex;align-items:center;justify-content:space-between;gap:10px}
.colSearch{position:relative}
.colSearch input{width:100%;border:1px solid var(--line);background:#0b0f17;color:#fff;border-radius:10px;padding:10px 12px;outline:none;min-height:42px}
.colSearch input::placeholder{color:#667085}
.colH small{opacity:.82;font-weight:800;color:#cbd5e1;white-space:nowrap}
.listWrap{position:relative;display:flex;flex-direction:column;min-height:0;flex:1;overflow:hidden;background:linear-gradient(180deg,rgba(23,10,9,.18),rgba(8,4,4,.08))}
.listWrap::before,.listWrap::after{content:'';position:absolute;left:0;right:0;height:18px;pointer-events:none;z-index:2}
.listWrap::before{top:0;background:linear-gradient(180deg,rgba(20,9,8,.95),rgba(20,9,8,0))}
.listWrap::after{bottom:0;background:linear-gradient(0deg,rgba(20,9,8,.96),rgba(20,9,8,0))}
.list{height:100%;max-height:none;overflow:auto;position:relative;flex:1;min-height:0;overscroll-behavior:contain;overscroll-behavior-y:contain;scroll-behavior:smooth;scroll-snap-type:y proximity;scroll-padding:8px 0 18px;-webkit-overflow-scrolling:touch;touch-action:pan-y;scrollbar-gutter:stable;scrollbar-width:thin;scrollbar-color:rgba(212,175,55,.22) transparent}
.list:hover{scrollbar-color:rgba(212,175,55,.34) transparent}

.list::-webkit-scrollbar{width:6px;height:6px}

.list::-webkit-scrollbar-thumb{background:rgba(212,175,55,.18);border-radius:999px;border:1px solid transparent;background-clip:padding-box}
.list:hover::-webkit-scrollbar-thumb{background:rgba(212,175,55,.30)}
.list::-webkit-scrollbar-track{background:transparent}

.vpad{height:0;pointer-events:none}
.pager{display:none}
.pager.hidden{display:none}



.row{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 12px;border-bottom:1px dashed rgba(255,255,255,.08);cursor:pointer;height:56px;transition:background .15s ease,border-color .15s ease;scroll-snap-align:start}
.row:hover{background:rgba(212,175,55,.06)}
.row.active{background:rgba(212,175,55,.12)}
.left{display:flex;align-items:center;gap:10px;min-width:0}
.badge{width:22px;height:22px;border-radius:999px;background:rgba(212,175,55,.18);color:var(--acc);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:900;flex:0 0 auto;border:1px solid rgba(212,175,55,.35)}
.title{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sub{font-size:12px;color:#aab2bf;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.right{font-family:Consolas,monospace;color:#c2c8d2;font-size:12px;opacity:.9;flex:0 0 auto}
.empty{padding:26px 14px;color:#7b8695;text-align:center;scroll-snap-align:start}
.route-card{padding:12px 12px 10px;border-bottom:1px dashed rgba(255,255,255,.10);scroll-snap-align:start}
.route-card-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.route-card-title{font-weight:900;color:var(--acc)}
.route-card-meta{font-size:12px;color:#a48a63}
.route-steps{display:grid;gap:6px}
.route-step{line-height:1.7;color:#ddd}
.route-step-index{display:inline-block;min-width:22px;color:var(--acc);font-weight:900}


.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px;align-items:stretch}
.card{background:linear-gradient(180deg,rgba(42,22,18,.96),rgba(20,9,8,.98));border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:var(--shadow-soft);min-height:100%}

.cardImg{height:164px;background:radial-gradient(circle at 20% 20%,rgba(212,175,55,.20),transparent 60%),#130605;display:flex;align-items:center;justify-content:center;color:var(--acc-hover);font-weight:900}

.cardImg img{width:100%;height:100%;object-fit:cover}
.cardB{padding:14px}
.cardT{font-weight:900;margin-bottom:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#fff}
.cardD{color:#aab2bf;font-size:12px;min-height:38px;white-space:pre-wrap;line-height:1.7}
.cardA{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
.cardA .btn{flex:1 1 120px;text-align:center}
.homeLiteBar{padding:2px 0 12px}
.homeLiteBar input{width:100%;border:1px solid var(--line);background:#0b0f17;color:#fff;border-radius:10px;padding:10px 12px;outline:none;min-height:42px}
.homeLiteBar input::placeholder{color:#667085}
.homeTags{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.tagBtn{border:1px solid rgba(212,175,55,.3);background:linear-gradient(180deg,#8b2a1e,#5f1b13);color:#fff;padding:9px 13px;border-radius:10px;font-weight:900;cursor:pointer;min-height:40px;box-shadow:0 10px 20px rgba(95,27,19,.22)}

.tagBtn:hover{filter:brightness(1.06)}
.foot{padding:12px 16px;color:#a48a63;text-align:center;font-size:12px;background:rgba(12,5,4,.88);border-top:1px solid var(--line)}


</style>
</head><body>

<div class="header">
  <div class="inner">
    <div class="brand">
      <h1 id="hdrName">虾米网络</h1>
      <div class="sub" id="hdrSub">Legend of Mir 2 Private Server</div>
    </div>
    <div class="nav">
      <a href="./index.html" id="hdrNavHome">官网首页</a>
      <a href="./droprate.html" id="hdrNavDrop" class="active">爆率查询</a>
    </div>


  </div>
</div>

<div class="app">
  <div class="topbar">
    <div class="brand2">
      <div class="logoDot">战</div>
      <div id="siteTitle">玛法情报中心</div>
    </div>
    <div class="nav2">
      <a href="./index.html" class="navBtn" style="text-decoration:none;display:inline-flex;align-items:center;justify-content:center">官网首页</a>
      <button class="navBtn active" data-tab="home">全部版本</button>


      <button class="navBtn" data-tab="item">物品查询</button>
      <button class="navBtn" data-tab="monster">怪物查询</button>
      <button class="navBtn" data-tab="map">地图查询</button>
      <button class="navBtn" data-tab="npc">NPC查询</button>
      <a href="#" class="navBtn disabled" id="guideBtn" target="_blank" rel="noopener" style="text-decoration:none;display:inline-flex;align-items:center;justify-content:center">攻略查询</a>
    </div>
    <div class="rightBox">
      <select class="sel" id="verSel"></select>
      <div class="pill" id="verInfo">选择查询版本</div>
    </div>
  </div>

  <div class="toolbar">
    <div class="search">
      <div class="modeWrap">
        <button class="modeBtn active" id="modeStd" type="button">标准模式</button>
        <button class="modeBtn" id="modeLite" type="button">精简模式</button>
      </div>
      <select id="sortSel" class="btn mini">
        <option value="default">排序：默认</option>
        <option value="name">排序：名称</option>
        <option value="rate">排序：爆率(从高到低)</option>
      </select>
    </div>
    <div class="toolRight">
      <button class="btn" id="helpBtn" type="button">使用说明</button>
      <label class="check"><input type="checkbox" id="showAll" /> 显示全部（包含无掉落/无联动项）</label>
    </div>
  </div>

  <div class="content">
    <div id="viewHome" style="display:none">
      <div id="homeLite" style="display:none">
        <div class="homeLiteBar"><input id="homeKw" placeholder="搜索名称，版本内容标签..." /></div>
        <div class="homeTags" id="homeTags"></div>
      </div>
      <div class="cards" id="cards"></div>
      <div class="empty" id="homeEmpty" style="display:none">未配置任何版本，请先在工具箱里添加爆率查询版本</div>
    </div>

    <div id="viewMain" style="display:none">
      <div class="grid4">
        <div class="col"><div class="colH"><div class="colTitle"><span id="h1">物品名称</span><small id="h1s"></small></div><div class="colSearch"><input id="ckw1" placeholder="请输入关键词过滤" /></div></div><div class="listWrap"><div class="list" id="l1"></div><div class="pager hidden" id="p1"></div></div></div>
        <div class="col"><div class="colH"><div class="colTitle"><span id="h2">物品出处</span><small id="h2s"></small></div><div class="colSearch"><input id="ckw2" placeholder="请输入关键词过滤" /></div></div><div class="listWrap"><div class="list" id="l2"></div><div class="pager hidden" id="p2"></div></div></div>
        <div class="col"><div class="colH"><div class="colTitle"><span id="h3">刷新地图</span><small id="h3s"></small></div><div class="colSearch"><input id="ckw3" placeholder="请输入关键词过滤" /></div></div><div class="listWrap"><div class="list" id="l3"></div><div class="pager hidden" id="p3"></div></div></div>
        <div class="col"><div class="colH"><div class="colTitle"><span id="h4">地图走法</span><small id="h4s"></small></div><div class="colSearch"><input id="ckw4" placeholder="请输入关键词过滤" /></div></div><div class="listWrap"><div class="list" id="l4"></div><div class="pager hidden" id="p4"></div></div></div>
      </div>

    </div>
  </div>

  <div class="foot" id="footTxt">游戏查询系统 - 虾米工具箱生成</div>
</div>

<script>
function esc(s){return String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function el(id){return document.getElementById(id);}
function qsp(){return Object.fromEntries(new URLSearchParams(location.search));}
const _CACHE_DB_NAME='xm_drop_cache_v1';
const _CACHE_STORE_NAME='files';
let _CACHE_DB_PROM=null;
function _openCacheDb(){
  if(_CACHE_DB_PROM) return _CACHE_DB_PROM;
  _CACHE_DB_PROM = new Promise(resolve=>{
    try{
      if(!('indexedDB' in window)){ resolve(null); return; }
      const req = indexedDB.open(_CACHE_DB_NAME, 1);
      req.onupgradeneeded = function(){
        try{
          const db = req.result;
          if(db && !db.objectStoreNames.contains(_CACHE_STORE_NAME)){
            db.createObjectStore(_CACHE_STORE_NAME);
          }
        }catch(e){}
      };
      req.onsuccess = function(){ resolve(req.result || null); };
      req.onerror = function(){ resolve(null); };
    }catch(e){ resolve(null); }
  });
  return _CACHE_DB_PROM;
}
async function _cacheGet(key){
  const db = await _openCacheDb();
  if(!db) return null;
  return await new Promise(resolve=>{
    try{
      const tx = db.transaction(_CACHE_STORE_NAME, 'readonly');
      const st = tx.objectStore(_CACHE_STORE_NAME);
      const rq = st.get(key);
      rq.onsuccess = function(){ resolve(rq.result || null); };
      rq.onerror = function(){ resolve(null); };
    }catch(e){ resolve(null); }
  });
}
async function _cacheSet(key, val){
  const db = await _openCacheDb();
  if(!db) return false;
  return await new Promise(resolve=>{
    try{
      const tx = db.transaction(_CACHE_STORE_NAME, 'readwrite');
      const st = tx.objectStore(_CACHE_STORE_NAME);
      st.put(val, key);
      tx.oncomplete = function(){ resolve(true); };
      tx.onerror = function(){ resolve(false); };
      tx.onabort = function(){ resolve(false); };
    }catch(e){ resolve(false); }
  });
}
function _cacheKeyForUrl(url){
  try{ return new URL(String(url||''), location.href).toString(); }catch(e){ return String(url||''); }
}

/* 兼容旧缓存文本与 UTF-8 BOM，统一将 JSON 内容安全解析为对象。 */
function parseJsonPayload(raw){
  const txt = String(raw || '').replace(/^\uFEFF/, '').trim();
  if(!txt) return null;
  return JSON.parse(txt);
}

/* 兼容旧缓存结构与新对象缓存，尽量避免重复 JSON 字符串驻留。 */
function readCachedJsonValue(cached){
  if(!cached || typeof cached !== 'object') return null;
  if(cached.data && typeof cached.data === 'object') return cached.data;
  if(cached.text) return parseJsonPayload(cached.text);
  return null;
}

/* 远程 JSON 优先使用原生对象解析，失败时回退到文本模式确保兼容。 */
async function readRemoteJson(resp){
  try{
    const data = await resp.clone().json();
    return {data:data, cacheValue:{t:Date.now(), data:data}};
  }catch(e){}
  const txt = await resp.text();
  await new Promise(r=>setTimeout(r,0));
  return {data:parseJsonPayload(txt), cacheValue:{t:Date.now(), text:txt}};
}

function setTabActive(tab){

  document.querySelectorAll('.navBtn').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.navBtn').forEach(b=>{ if(b.getAttribute('data-tab')===tab) b.classList.add('active'); });
}
function setView(tab){
  if(tab==='home'){ el('viewHome').style.display='block'; el('viewMain').style.display='none'; clearAllPagers(); return; }
  el('viewHome').style.display='none'; el('viewMain').style.display='block';
}

let SITE=null;
let CURRENT=null;
let DATA=null;
let STATE={tab:'home', mode:'std', sort:'default', homeKw:'', kw1:'', kw2:'', kw3:'', kw4:'', showAll:false, showRate:true, sel1:'', sel2:'', sel3:'', sel4:''};
let IDX={items:[], itemsAll:[], itemsDb:[], itemsDrop:[], itemsDropDisplay:[], itemDrops:{}, itemMinDen:{}, itemRows:{all:{default:[],name:[],rate:[]},drop:{default:[],name:[],rate:[]}}, monsters:[], monstersAll:[], monstersDrop:[], monsterRows:{all:{default:[],name:[]},drop:{default:[],name:[]}}, monByName:{}, monByNorm:{}, maps:[], mapRows:{default:[],name:[]}, mapByKey:{}, routesByFrom:{}, routesByTo:{}, npcs:[], npcRows:{default:[],name:[]}, npcByName:{}, npcRoutesByTo:{}}; 
let ROUTE_CACHE={chains:new Map(), direct:new Map(), order:[]};
let VIEW_CACHE={itemDrops:{}, monsterItems:{}, monsterMaps:{}, mapMonsters:{}, mapRouteRows:{}, npcLocs:{}};
let _RENDER_TIMER=null;
let _LIST_CLICK_BOUND=false;
let _AUTO_PAGE_SCROLL_BOUND=false;
const PAGE_SIZE_DEFAULT=100000;
const PAGE_SIZE_ROUTE=100000;
const VLIST_ROW_HEIGHT=56;
const VLIST_BUFFER=8;
const AUTO_PAGE_TRIGGER_GAP=120;

let PAGE_STATE={l1:1,l2:1,l3:1,l4:1};



function scheduleRender(){
  try{ if(_RENDER_TIMER) clearTimeout(_RENDER_TIMER); }catch(e){}
  _RENDER_TIMER = setTimeout(function(){
    _RENDER_TIMER = null;
    try{ if(STATE.tab!=='home') render(); }catch(e){}
  }, 160);
}

function resetViewCache(){
  VIEW_CACHE={itemDrops:{}, monsterItems:{}, monsterMaps:{}, mapMonsters:{}, mapRouteRows:{}, npcLocs:{}};
}

/* 使用 requestAnimationFrame 合并滚动中的虚拟列表刷新，降低连续重排频率。 */
function scheduleVirtualViewport(node){
  if(!node || !node._vmeta || node._vraf) return;
  const raf = (window && window.requestAnimationFrame) ? window.requestAnimationFrame.bind(window) : function(fn){ return setTimeout(fn, 16); };
  node._vraf = raf(function(){
    node._vraf = 0;
    renderVirtualViewport(node);
  });
}

function itemOverallDen(it){

  const den = Number(it && it.den || 0);
  const gd = Number(it && it.group_den || 0);
  if(!den) return 0;
  if(gd > 0) return den * gd;
  return den;
}

function hasRealDropEntry(it){
  const obj = it || {};
  const nm = String(obj.name || obj.item || obj.title || '').trim();
  if(!nm) return false;
  return itemOverallDen(obj) > 0;
}

function getRealMonsterDrops(mon){
  const arr = (mon && Array.isArray(mon.items)) ? mon.items : [];
  return dedupeMonItems(arr).filter(hasRealDropEntry);
}

function hasStrictRealDropEntry(it){
  const obj = it || {};
  const nm = String(obj.name || obj.item || obj.title || '').trim();
  if(!nm) return false;
  if(/^=+\s*.*?\s*=+$/.test(nm)) return false;
  if(/[<$][A-Z$]/i.test(nm) || /\$STR\s*\(/i.test(nm)) return false;
  return itemOverallDen(obj) > 0;
}

function getStrictRealMonsterDrops(mon){
  const arr = (mon && Array.isArray(mon.items)) ? mon.items : [];
  return dedupeMonItems(arr).filter(hasStrictRealDropEntry);
}

function hasRealMonsterDrops(mon){
  return getStrictRealMonsterDrops(mon).length > 0;
}

function hasRenderableMonsterDropsByName(name){
  const mon = getMonsterByName(name);
  return hasRealMonsterDrops(mon);
}

function getMonsterNamesWithRealDrops(){
  const src = (DATA && Array.isArray(DATA.monsters)) ? DATA.monsters : [];
  const out = [];
  for(let i=0;i<src.length;i++){
    const mon = src[i] || {};
    const name = String((mon && (mon.monster || mon.name)) || '').trim();
    if(!name) continue;
    if(hasRealMonsterDrops(mon)) out.push(name);
  }
  return dedupeList(out);
}

function dedupeMonItems(items){
  const by = {};
  const order = [];
  const arr = Array.isArray(items) ? items : [];
  for(let i=0;i<arr.length;i++){
    const it = arr[i] || {};
    const nm = String(it.name||'').trim();
    if(!nm) continue;
    const den = itemOverallDen(it);
    if(!den) continue;
    const prev = by[nm];
    if(!prev){
      by[nm] = it;
      order.push(nm);
      continue;
    }
    if(itemOverallDen(prev) > den) by[nm] = it;
  }
  return order.map(n=>by[n]);
}

function buildNameRows(list){
  const src = Array.isArray(list) ? list : [];
  const rows = [];
  for(let i=0;i<src.length;i++){
    const name = String(src[i]||'').trim();
    if(!name) continue;
    rows.push({key:name, badge:rows.length+1, title:name, _search:name.toLowerCase()});
  }
  return rows;
}

function dedupeDisplayRows(rows){
  const src = Array.isArray(rows) ? rows : [];
  const out = [];
  const seen = {};
  for(let i=0;i<src.length;i++){
    const r = src[i] || {};
    const sig = [String(r.title||''), String(r.sub||''), String(r.right||'')].join('|');
    if(!sig || seen[sig]) continue;
    seen[sig] = 1;
    out.push(Object.assign({}, r, {badge: out.length + 1}));
  }
  return out;
}

function dedupeList(list){
  const src = Array.isArray(list) ? list : [];
  const out = [];
  const seen = {};
  for(let i=0;i<src.length;i++){
    const v = String(src[i] || '').trim();
    if(!v || seen[v]) continue;
    seen[v] = 1;
    out.push(v);
  }
  return out;
}

function filterNameRowsByKw(rows, kwRaw){
  const kw = String(kwRaw||'').trim().toLowerCase();
  const src = Array.isArray(rows) ? rows : [];
  if(!kw) return src.slice();
  const tokens = kw.split(/\s+/).filter(Boolean);
  if(!tokens.length) return src.slice();
  return src.filter(r=>{
    const t = String((r && r._search) || (r && r.title) || '').toLowerCase();
    for(let i=0;i<tokens.length;i++){
      if(t.indexOf(tokens[i]) < 0) return false;
    }
    return true;
  });
}

function itemSortValue(name){
  return Number((IDX.itemMinDen && IDX.itemMinDen[name]) || 1e18);
}

function rebuildPrimaryRows(){
  const itemAll = Array.isArray(IDX.itemsAll) ? IDX.itemsAll.slice() : [];
  const itemDrop = Array.isArray(IDX.itemsDropDisplay) ? IDX.itemsDropDisplay.slice() : [];
  const monAll = Array.isArray(IDX.monstersAll) ? IDX.monstersAll.slice() : [];
  const monDrop = Array.isArray(IDX.monstersDrop) ? IDX.monstersDrop.slice() : [];
  const mapNames = Array.isArray(IDX.maps) ? IDX.maps.map(x=>String(x && x.name || '').trim()).filter(Boolean) : [];
  const npcNames = Array.isArray(IDX.npcs) ? IDX.npcs.slice() : [];

  IDX.itemRows.all.default = buildNameRows(itemAll);
  IDX.itemRows.all.name = buildNameRows(itemAll.slice().sort(_sortName));
  IDX.itemRows.all.rate = buildNameRows(itemAll.slice().sort((a,b)=>itemSortValue(a)-itemSortValue(b)));
  IDX.itemRows.drop.default = buildNameRows(itemDrop);
  IDX.itemRows.drop.name = buildNameRows(itemDrop.slice().sort(_sortName));
  IDX.itemRows.drop.rate = buildNameRows(itemDrop.slice().sort((a,b)=>itemSortValue(a)-itemSortValue(b)));

  IDX.monsterRows.all.default = buildNameRows(monAll);
  IDX.monsterRows.all.name = buildNameRows(monAll.slice().sort(_sortName));
  IDX.monsterRows.drop.default = buildNameRows(monDrop);
  IDX.monsterRows.drop.name = buildNameRows(monDrop.slice().sort(_sortName));

  IDX.mapRows.default = buildNameRows(mapNames);
  IDX.mapRows.name = buildNameRows(mapNames.slice().sort(_sortName));

  IDX.npcRows.default = buildNameRows(npcNames);
  IDX.npcRows.name = buildNameRows(npcNames.slice().sort(_sortName));
}

function baseItemRows(){
  const scope = STATE.showAll ? 'all' : 'drop';
  if(STATE.sort === 'name') return IDX.itemRows[scope].name || [];
  if(STATE.sort === 'rate') return IDX.itemRows[scope].rate || [];
  return IDX.itemRows[scope].default || [];
}

function baseMonsterRows(){
  const scope = STATE.showAll ? 'all' : 'drop';
  if(STATE.sort === 'name') return IDX.monsterRows[scope].name || [];
  return IDX.monsterRows[scope].default || [];
}

function baseMapRows(){
  if(STATE.sort === 'name') return IDX.mapRows.name || [];
  return IDX.mapRows.default || [];
}

function baseNpcRows(){
  if(STATE.sort === 'name') return IDX.npcRows.name || [];
  return IDX.npcRows.default || [];
}

function getItemDropRows(itemName){
  const key = String(itemName||'').trim();
  if(!key) return [];
  if(VIEW_CACHE.itemDrops[key]) return VIEW_CACHE.itemDrops[key];
  const drops = (IDX.itemDrops[key] || []).slice();
  drops.sort((a,b)=>Number(a.den||0)-Number(b.den||0));
  const rows = drops.map((d,i)=>({key:d.monster, badge:i+1, title:d.monster, right:(STATE.showRate ? ('1/'+d.den) : '')}));
  VIEW_CACHE.itemDrops[key] = rows;
  return rows;
}

function getMonsterItemRows(monName){
  const key = String(monName||'').trim();
  if(!key) return [];
  if(VIEW_CACHE.monsterItems[key]) return VIEW_CACHE.monsterItems[key];
  const mon = IDX.monByName[key] || null;
  const its = mon && Array.isArray(mon.items) ? dedupeMonItems(mon.items) : [];
  its.sort((a,b)=>itemOverallDen(a)-itemOverallDen(b));
  const rows = its.map((it,i)=>({key:it.name, badge:i+1, title:it.name, right:(STATE.showRate ? ('1/'+itemOverallDen(it)) : '')}));
  VIEW_CACHE.monsterItems[key] = rows;
  return rows;
}

function getMonsterMapRows(monName){
  const key = String(monName||'').trim();
  if(!key) return [];
  if(VIEW_CACHE.monsterMaps[key]) return VIEW_CACHE.monsterMaps[key];
  const mon = IDX.monByName[key] || null;
  const sp = mon && Array.isArray(mon.spawns) ? mon.spawns.slice() : [];
  const grouped = {};
  const order = [];
  for(let i=0;i<sp.length;i++){
    const s = sp[i] || {};
    const raw = String((s && (s.map||s.map_code)) || '').trim() || String((s && (s.map_name||s.map)) || '').trim();
    const code = resolveMapCode(raw);
    if(!code) continue;
    if(!grouped[code]){
      const nm = String((s && s.map_name) || '').trim();
      grouped[code] = {code:code, title:(mapLabel(code) || nm || raw || code), points:0, total:0, minTime:null, minTimeText:null, sample:[]};
      order.push(code);
    }
    const g = grouped[code];
    g.points += 1;
    const cx = Number(s.x||0), cy = Number(s.y||0);
    if(g.sample.length < 3) g.sample.push(String(cx)+','+String(cy));
    g.total += Number(s.count||0);
    const ttext = String((s && (s.time_text||s.timeText)) || '').trim();
    if(ttext){
      if(!g.minTimeText) g.minTimeText = ttext;
    }else if(!g.minTimeText){
      const tv = Number(s.time||0);
      if(g.minTime == null) g.minTime = tv;
      else if(tv > 0 && (g.minTime === 0 || tv < g.minTime)) g.minTime = tv;
    }
  }
  const rows = order.map((code,i)=>{
    const g = grouped[code] || {};
    let sub = '点数 ' + Number(g.points||0);
    if(g.sample && g.sample.length){
      sub += ' | 坐标 ' + g.sample.join(' ') + (Number(g.points||0) > g.sample.length ? ' ...' : '');
    }
    if(g.code && g.title && g.title !== g.code) sub += ' | ' + g.code;
    const right = g.minTimeText ? (String(g.minTimeText) + '/' + Number(g.total||0) + '只') : ((Number(g.minTime||0))+'分/'+Number(g.total||0)+'只');
    return {key:g.code, badge:i+1, title:g.title||g.code, sub:sub, right:right};
  });
  VIEW_CACHE.monsterMaps[key] = rows;
  return rows;
}

function getMapMonsterRows(mapName){
  const key = resolveMapCode(mapName);
  if(!key) return [];
  if(VIEW_CACHE.mapMonsters[key]) return VIEW_CACHE.mapMonsters[key];
  const rows = mapMonsterGroups(key);
  VIEW_CACHE.mapMonsters[key] = rows;
  return rows;
}

function getDirectRouteRows(codeOrName){
  const code = resolveMapCode(codeOrName);
  if(!code) return [];
  if(VIEW_CACHE.mapRouteRows[code]) return VIEW_CACHE.mapRouteRows[code];
  const rts = mergeRouteEdges(directRoutesToMapCached(code), directNpcRoutesToMap(code));
  const rows = rts.map((r,i)=>{
    const from = String(r && r.from || '').trim();
    const to = String(r && r.to || '').trim();
    const fromName = String(r && (r.from_name || '') || '').trim() || mapLabel(from) || from;
    const toName = String(r && (r.to_name || '') || '').trim() || mapLabel(to) || to;
    const sub = routeStepText(r);
    return {key:'in#'+from+'#'+i, badge:i+1, title:fromName||toName, sub:sub, right:resolveMapCode(from)};
  });
  VIEW_CACHE.mapRouteRows[code] = rows;
  return rows;
}

function getNpcLocationPack(npcName){
  const key = String(npcName||'').trim();
  if(!key) return {rows:[], byKey:{}};
  if(VIEW_CACHE.npcLocs[key]) return VIEW_CACHE.npcLocs[key];
  const locs = (IDX.npcByName[key] || []).slice();
  const pack = {rows:locs, byKey:{}};
  VIEW_CACHE.npcLocs[key] = pack;
  return pack;
}

function mapLabel(codeOrName){
  const k = String(codeOrName||'').trim();
  if(!k) return '';
  const mp = IDX.mapByKey[k] || IDX.mapByKey[k.toLowerCase()] || IDX.mapByKey[k.toUpperCase()] || null;
  if(mp){
    const nm = String(mp.name||'').trim();
    if(nm) return nm;
    const cd = String(mp.code||'').trim();
    if(cd) return cd;
  }
  return k;
}

function resolveMapCode(codeOrName){
  const k = String(codeOrName||'').trim();
  if(!k) return '';
  const mp = IDX.mapByKey[k] || IDX.mapByKey[k.toLowerCase()] || IDX.mapByKey[k.toUpperCase()] || null;
  const cd = mp ? String(mp.code||'').trim() : '';
  return cd || k;
}

function routesForMap(codeOrName){
  const code = resolveMapCode(codeOrName);
  if(!code) return [];
  const ls = (IDX.routesByFrom && (IDX.routesByFrom[code] || IDX.routesByFrom[code.toLowerCase()] || IDX.routesByFrom[code.toUpperCase()])) || [];
  return Array.isArray(ls) ? ls : [];
}

function reverseEdgeNonNpc(e){
  const fromKey = String(e && (e._fromKey || e.from) || '').trim();
  const toKey = String(e && (e._toKey || e.to) || '').trim();
  if(!fromKey || !toKey) return null;
  const via = String(e && (e.via||'') || '').trim();
  if(via === 'npc') return null;
  const r2 = {
    from: toKey,
    to: fromKey,
    from_x: (e && e.to_x != null) ? e.to_x : '',
    from_y: (e && e.to_y != null) ? e.to_y : '',
    to_x: (e && e.from_x != null) ? e.from_x : '',
    to_y: (e && e.from_y != null) ? e.from_y : ''
  };
  try{ r2._fromKey = toKey; r2._toKey = fromKey; }catch(ex){}
  try{ r2.from_name = mapLabel(toKey) || String(e && e.to_name || '').trim() || toKey; }catch(ex2){}
  try{ r2.to_name = mapLabel(fromKey) || String(e && e.from_name || '').trim() || fromKey; }catch(ex3){}
  return r2;
}

function predEdgesToKey(curKey){
  const byTo = IDX.routesByTo || {};
  const byFrom = IDX.routesByFrom || {};
  const a = [];
  let inc = byTo[curKey] || byTo[String(curKey||'').toLowerCase()] || byTo[String(curKey||'').toUpperCase()] || [];
  if(inc && inc.length){
    if(inc.length > 250) inc = inc.slice(0, 250);
    a.push.apply(a, inc);
  }
  const outs = byFrom[curKey] || byFrom[String(curKey||'').toLowerCase()] || byFrom[String(curKey||'').toUpperCase()] || [];
  for(let i=0;i<Math.min(200, outs.length);i++){
    const r2 = reverseEdgeNonNpc(outs[i]);
    if(r2) a.push(r2);
  }
  return a;
}

function directRoutesToMap(codeOrName){
  const target = resolveMapCode(codeOrName);
  if(!target) return [];
  const preds = predEdgesToKey(target);
  return Array.isArray(preds) ? preds : [];
}

function directRoutesToMapCached(codeOrName){
  const target = resolveMapCode(codeOrName);
  if(!target) return [];
  try{
    const hit = ROUTE_CACHE.direct.get(target);
    if(hit) return hit;
  }catch(e){}
  const v = directRoutesToMap(target);
  try{
    ROUTE_CACHE.direct.set(target, v);
    ROUTE_CACHE.order.push(target);
    if(ROUTE_CACHE.order.length > 220){
      const drop = ROUTE_CACHE.order.shift();
      try{ ROUTE_CACHE.direct.delete(drop); }catch(e2){}
      try{ ROUTE_CACHE.chains.delete(drop); }catch(e3){}
    }
  }catch(e4){}
  return v;
}

function routeChainsToMap(codeOrName){
  const target = resolveMapCode(codeOrName);
  if(!target) return [];
  const maxDepth = 14;
  const maxPaths = 80;
  const out = [];
  const seenKeys = new Set();

  const roots = (IDX && Array.isArray(IDX._routeRoots)) ? IDX._routeRoots : [];
  const rootSet = new Set(roots || []);

  function _sig(path){
    try{
      return path.map(e=>{
        const f = String(e && (e._fromKey||e.from||'')||'').trim();
        const t = String(e && (e._toKey||e.to||'')||'').trim();
        const fx = (e && e.from_x != null) ? e.from_x : '';
        const fy = (e && e.from_y != null) ? e.from_y : '';
        const tx = (e && e.to_x != null) ? e.to_x : '';
        const ty = (e && e.to_y != null) ? e.to_y : '';
        const via = String(e && (e.via||'') || '').trim();
        const npc = String(e && (e.npc||'') || '').trim();
        const rr = (e && e.r != null && e.r !== '') ? e.r : '';
        return f+':'+fx+','+fy+'>'+t+':'+tx+','+ty+':'+via+':'+npc+':'+rr;
      }).join('|');
    }catch(e){
      return '';
    }
  }

  let expansions = 0;
  const maxExpansions = 6500;
  const q = [{key: target, depth: 0, nodes: [target], rev: []}];
  while(q.length && out.length < maxPaths && expansions < maxExpansions){
    const cur = q.shift();
    if(!cur) break;
    const curKey = cur.key;
    if(cur.rev.length && rootSet.size && rootSet.has(curKey)){
      const path = cur.rev.slice().reverse();
      const k = _sig(path);
      if(k && !seenKeys.has(k)){
        seenKeys.add(k);
        out.push(path);
      }
      continue;
    }
    if(cur.depth >= maxDepth) continue;
    const preds = predEdgesToKey(curKey);
    if(!preds || !preds.length) continue;
    const limit = Math.min(120, preds.length);
    for(let i=0;i<limit && out.length < maxPaths && expansions < maxExpansions;i++){
      const e = preds[i];
      const pk = String(e && (e._fromKey || e.from) || '').trim();
      if(!pk) continue;
      if(cur.nodes.indexOf(pk) >= 0) continue;
      expansions += 1;
      const nodes2 = cur.nodes.slice();
      nodes2.push(pk);
      const rev2 = cur.rev.slice();
      rev2.push(e);
      q.push({key: pk, depth: cur.depth + 1, nodes: nodes2, rev: rev2});
    }
  }
  if(out.length){
    out.sort((a,b)=>a.length-b.length);
    return out;
  }

  const direct = predEdgesToKey(target);
  if(direct && direct.length){
    const chains = [];
    for(let i=0;i<Math.min(60, direct.length);i++){
      const e = direct[i];
      const path = [e];
      const k = _sig(path);
      if(k && !seenKeys.has(k)){
        seenKeys.add(k);
        chains.push(path);
      }
    }
    chains.sort((a,b)=>a.length-b.length);
    return chains;
  }
  return [];
}

function routeChainsToMapCached(codeOrName){
  const target = resolveMapCode(codeOrName);
  if(!target) return [];
  try{
    const hit = ROUTE_CACHE.chains.get(target);
    if(hit) return hit;
  }catch(e){}
  const v = routeChainsToMap(target);
  try{
    ROUTE_CACHE.chains.set(target, v);
    ROUTE_CACHE.order.push(target);
    if(ROUTE_CACHE.order.length > 220){
      const drop = ROUTE_CACHE.order.shift();
      try{ ROUTE_CACHE.direct.delete(drop); }catch(e2){}
      try{ ROUTE_CACHE.chains.delete(drop); }catch(e3){}
    }
  }catch(e4){}
  return v;
}

function directNpcRoutesToMap(codeOrName){
  const target = resolveMapCode(codeOrName);
  if(!target) return [];
  const by = IDX.npcRoutesByTo || {};
  const arr = by[target] || by[String(target).toLowerCase()] || by[String(target).toUpperCase()] || [];
  return Array.isArray(arr) ? arr : [];
}

function mergeRouteEdges(base, extra){
  const out = [];
  const seen = {};
  function _sig(e){
    const f = String(e && (e._fromKey || e.from) || '').trim().toLowerCase();
    const t = String(e && (e._toKey || e.to) || '').trim().toLowerCase();
    const fx = (e && e.from_x != null) ? String(e.from_x) : '';
    const fy = (e && e.from_y != null) ? String(e.from_y) : '';
    const tx = (e && e.to_x != null) ? String(e.to_x) : '';
    const ty = (e && e.to_y != null) ? String(e.to_y) : '';
    const via = String(e && (e.via || '') || '').trim().toLowerCase();
    const npc = String(e && (e.npc || '') || '').trim().toLowerCase();
    const rr = (e && e.r != null && e.r !== '') ? String(e.r) : '';
    return f+'>'+t+'|'+fx+','+fy+'>'+tx+','+ty+'|'+via+'|'+npc+'|'+rr;
  }
  const merged = []
    .concat(Array.isArray(base) ? base : [])
    .concat(Array.isArray(extra) ? extra : []);
  for(let i=0;i<merged.length;i++){
    const r = merged[i];
    const k = _sig(r);
    if(!k || seen[k]) continue;
    seen[k] = 1;
    out.push(r);
  }
  return out;
}

function mergeRouteChains(base, extra){
  const out = [];
  const seen = {};
  function _edgeSig(e){
    const f = String(e && (e._fromKey || e.from) || '').trim().toLowerCase();
    const t = String(e && (e._toKey || e.to) || '').trim().toLowerCase();
    const fx = (e && e.from_x != null) ? String(e.from_x) : '';
    const fy = (e && e.from_y != null) ? String(e.from_y) : '';
    const tx = (e && e.to_x != null) ? String(e.to_x) : '';
    const ty = (e && e.to_y != null) ? String(e.to_y) : '';
    const via = String(e && (e.via || '') || '').trim().toLowerCase();
    const npc = String(e && (e.npc || '') || '').trim().toLowerCase();
    const rr = (e && e.r != null && e.r !== '') ? String(e.r) : '';
    const randomTo = !!(e && (e.random_to || e.randomTo));
    return f+'>'+t+'|'+fx+','+fy+'>'+tx+','+ty+'|'+via+'|'+npc+'|'+rr+'|'+String(randomTo);
  }
  function _pathSig(path){
    const arr = Array.isArray(path) ? path : [];
    if(!arr.length) return '';
    return arr.map(_edgeSig).join('||');
  }
  const merged = []
    .concat(Array.isArray(base) ? base : [])
    .concat(Array.isArray(extra) ? extra : []);
  for(let i=0;i<merged.length;i++){
    const p = merged[i];
    const k = _pathSig(p);
    if(!k || seen[k]) continue;
    seen[k] = 1;
    out.push(p);
  }
  return out;
}

function formatRouteChain(path){
  if(!path || !path.length) return '';
  const names = [];
  for(let i=0;i<path.length;i++){
    const r = path[i] || {};
    const fromKey = String(r._fromKey || r.from || '').trim();
    const toKey = String(r._toKey || r.to || '').trim();
    const fromName = String(r.from_name || '').trim() || mapLabel(fromKey) || fromKey;
    const toName = String(r.to_name || '').trim() || mapLabel(toKey) || toKey;
    if(i === 0) names.push(String(fromName||'').trim());
    names.push(String(toName||'').trim());
  }
  return names.filter(Boolean).join('→');
}

function normalizeMonsterName(name){
  return String(name||'')
    .trim()
    .toLowerCase()
    .replace(/[·•‧・·﹒.]/g, '')
    .replace(/[-—–_\\s]+/g, '');
}

function getMonsterByName(name){
  const raw = String(name||'').trim();
  if(!raw) return null;
  const direct = IDX.monByName[raw] || null;
  const norm = IDX.monByNorm[normalizeMonsterName(raw)] || null;
  if(direct && hasRealMonsterDrops(direct)) return direct;
  if(norm && hasRealMonsterDrops(norm)) return norm;
  return direct || norm || null;
}

function formatMoveSub(fromName, fx, fy, toName, tx, ty, randomTo){
  let left = String(fromName||'').trim();
  let right = String(toName||'').trim();
  const hasF = (fx!=='' && fy!=='');
  const hasT = (tx!=='' && ty!=='');
  if(hasF) left += (left ? ' ' : '') + String(fx) + ',' + String(fy);
  if(hasT) right += (right ? ' ' : '') + String(tx) + ',' + String(ty);
  else if(randomTo) right += (right ? ' ' : '') + '随机坐标';
  if(left && right) return left + ' -> ' + right;
  return left || right || '';
}

function routeStepText(r){
  const fromKey = String(r && (r._fromKey || r.from) || '').trim();
  const toKey = String(r && (r._toKey || r.to) || '').trim();
  const fromName = String(r && r.from_name || '').trim() || mapLabel(fromKey) || fromKey;
  const toName = String(r && r.to_name || '').trim() || mapLabel(toKey) || toKey;
  const fx = (r && r.from_x != null) ? r.from_x : '';
  const fy = (r && r.from_y != null) ? r.from_y : '';
  const tx = (r && r.to_x != null) ? r.to_x : '';
  const ty = (r && r.to_y != null) ? r.to_y : '';
  const randomTo = !!(r && (r.random_to || r.randomTo));
  let a = String(fromName||'').trim();
  let b = String(toName||'').trim();
  const hasF = (fx!=='' && fy!=='');
  const hasT = (tx!=='' && ty!=='');
  if(hasF) a += (a ? ' ' : '') + String(fx) + ',' + String(fy);
  if(hasT) b += (b ? ' ' : '') + String(tx) + ',' + String(ty);
  else if(randomTo) b += (b ? ' ' : '') + '随机坐标';
  const base = (a && b) ? (a + '→' + b) : (a || b || '');
  const via = String(r && (r.via || '') || '').trim().toLowerCase();
  if(via === 'npc'){
    const npc = String(r && (r.npc || '') || '').trim();
    const rr = (r && r.r != null && r.r !== '') ? r.r : '';
    let extra = ' | NPC传送';
    if(npc) extra += ' [' + npc + ']';
    if(rr!=='') extra += ' 范围' + rr;
    return (base || (toName || fromName || '')) + extra;
  }
  return base;
}

/* 地图走法改为滑动到底自动续载，避免出现手动翻页按钮。 */
function renderRouteMethods(node, chains){
  const listId = String(node && node.id || '').trim();
  if(!chains || !chains.length){
    node.innerHTML = '<div class="empty">暂无地图走法数据</div>';
    node._pageMeta = null;
    setListHeaderStat(listId, 0, 0);
    clearPager(listId);
    return;
  }
  const page = syncPage(listId, chains.length, PAGE_SIZE_ROUTE);
  const prevPage = Number(node.getAttribute('data-page') || 0) || 0;
  const keepScroll = !!node._keepScrollOnAppend;
  node._keepScrollOnAppend = false;
  node.setAttribute('data-page', String(page));
  const view = chains.slice(0, page * PAGE_SIZE_ROUTE);
  node._pageMeta = {listId:listId, total:chains.length, pageSize:PAGE_SIZE_ROUTE, loaded:view.length};
  setListHeaderStat(listId, chains.length, view.length);

  let html = '';
  for(let i=0;i<view.length;i++){
    const p = view[i] || [];
    if(!p.length) continue;
    html += '<div class="route-card">';
    html += '<div class="route-card-head">';
    html += '<div class="route-card-title">' + esc('走法' + (i+1)) + '</div>';
    html += '<div class="route-card-meta">' + esc('共' + p.length + '步') + '</div>';
    html += '</div>';
    html += '<div class="route-steps">';
    for(let j=0;j<p.length;j++){
      const step = routeStepText(p[j]);
      html += '<div class="route-step">'
        + '<span class="route-step-index">' + esc(String(j+1) + '.') + '</span>'
        + '<span>' + esc(step) + '</span>'
        + '</div>';
    }
    html += '</div></div>';
  }

  node.innerHTML = html || '<div class="empty">暂无地图走法数据</div>';
  if(prevPage !== page && !keepScroll){
    try{ node.scrollTop = 0; }catch(e){}
  }
  renderPager(listId, chains.length, PAGE_SIZE_ROUTE, page);
}



function buildIndex(){
  IDX={items:[], itemsAll:[], itemsDb:[], itemsDrop:[], itemsDropDisplay:[], itemDrops:{}, itemMinDen:{}, itemRows:{all:{default:[],name:[],rate:[]},drop:{default:[],name:[],rate:[]}}, monsters:[], monstersAll:[], monstersDrop:[], monsterRows:{all:{default:[],name:[]},drop:{default:[],name:[]}}, monByName:{}, monByNorm:{}, maps:[], mapRows:{default:[],name:[]}, mapByKey:{}, routesByFrom:{}, routesByTo:{}, npcs:[], npcRows:{default:[],name:[]}, npcByName:{}, npcRoutesByTo:{}}; 
  try{ ROUTE_CACHE={chains:new Map(), direct:new Map(), order:[]}; }catch(e){}
  resetViewCache();
  if(!DATA) return;
  const hasPreDrops = (DATA && DATA.item_drops && typeof DATA.item_drops === 'object') ? true : false;
  const preDrops = hasPreDrops ? DATA.item_drops : null;
  const itemDropsMap = hasPreDrops ? null : {};
  const monsters = Array.isArray(DATA.monsters)?DATA.monsters:[];
  monsters.forEach(m=>{
    const name = String(m.monster||'').trim();
    if(!name) return;
    const prev = IDX.monByName[name];
    if(!prev || (hasRealMonsterDrops(m) && !hasRealMonsterDrops(prev))){
      IDX.monByName[name]=m;
    }
    const nk = normalizeMonsterName(name);
    if(nk){
      const prevNorm = IDX.monByNorm[nk];
      if(!prevNorm || (hasRealMonsterDrops(m) && !hasRealMonsterDrops(prevNorm))){
        IDX.monByNorm[nk] = m;
      }
    }
    IDX.monsters.push(name);
    if(!hasPreDrops){
      const items = Array.isArray(m.items)?m.items:[];
      items.forEach(it=>{
        const iname = String(it.name||'').trim();
        const den0 = Number(it.den||0);
        const den = den0 * (Number(it.group_den||0) > 0 ? Number(it.group_den||0) : 1);
        if(!iname || !den) return;
        if(!itemDropsMap[iname]) itemDropsMap[iname] = {};
        const prev = itemDropsMap[iname][name];
        if(prev == null || den < Number(prev||0)) itemDropsMap[iname][name] = den;
      });
    }
  });
  if(hasPreDrops && preDrops){
    try{
      const monsterItemMap = {};
      Object.keys(preDrops).forEach(iname=>{
        const raw = preDrops[iname];
        const arr = [];
        const a0 = Array.isArray(raw) ? raw : [];
        for(let i=0;i<a0.length;i++){
          const r = a0[i];
          if(Array.isArray(r)){
            const mon = String(r[0]||'').trim();
            const den = Number(r[1]||0);
            if(mon && den){
              arr.push({monster:mon, den:den});
              if(!monsterItemMap[mon]) monsterItemMap[mon] = [];
              monsterItemMap[mon].push({name:String(iname||'').trim(), den:den, group_den:1});
            }
          }else{
            const mon = String(r && r.monster || '').trim();
            const den = Number(r && r.den || 0);
            if(mon && den){
              arr.push({monster:mon, den:den});
              if(!monsterItemMap[mon]) monsterItemMap[mon] = [];
              monsterItemMap[mon].push({name:String(iname||'').trim(), den:den, group_den:1});
            }
          }
        }
        if(arr.length){
          IDX.itemDrops[iname] = arr;
          let minDen = 1e18;
          for(let j=0;j<arr.length;j++){
            const den = Number(arr[j] && arr[j].den || 0);
            if(den > 0 && den < minDen) minDen = den;
          }
          IDX.itemMinDen[iname] = minDen < 1e18 ? minDen : 1e18;
        }
      });
      Object.keys(monsterItemMap).forEach(monName=>{
        const nk = normalizeMonsterName(monName);
        const mon = IDX.monByName[monName] || (nk ? IDX.monByNorm[nk] : null) || null;
        if(!mon) return;
        mon.items = dedupeMonItems(monsterItemMap[monName]);
      });
    }catch(e){}
  }else{
    Object.keys(itemDropsMap).forEach(iname=>{
      const mm = itemDropsMap[iname] || {};
      const arr = [];
      Object.keys(mm).forEach(mon=>{
        const den = Number(mm[mon]||0);
        if(mon && den) arr.push({monster:mon, den:den});
      });
      IDX.itemDrops[iname] = arr;
      let minDen = 1e18;
      for(let i=0;i<arr.length;i++){
        const den = Number(arr[i] && arr[i].den || 0);
        if(den > 0 && den < minDen) minDen = den;
      }
      IDX.itemMinDen[iname] = minDen < 1e18 ? minDen : 1e18;
    });
  }
  IDX.itemsDrop = Object.keys(IDX.itemDrops);
  IDX.itemsDb = Array.isArray(DATA.all_items_db) ? DATA.all_items_db.map(x=>String(x||'').trim()).filter(Boolean) : [];
  IDX.itemsAll = Array.isArray(DATA.all_items) ? DATA.all_items.map(x=>String(x||'').trim()).filter(Boolean) : IDX.itemsDrop.slice();
  if(IDX.itemsDb && IDX.itemsDb.length){
    const dbSet = new Set(IDX.itemsDb.map(x=>String(x||'').trim().toLowerCase()).filter(Boolean));
    IDX.itemsDropDisplay = IDX.itemsDrop.filter(x=>dbSet.has(String(x||'').trim().toLowerCase()));
    const ratio = IDX.itemsDrop.length ? (IDX.itemsDropDisplay.length / IDX.itemsDrop.length) : 0;
    if((!IDX.itemsDropDisplay.length) || ratio < 0.2){
      IDX.itemsDropDisplay = IDX.itemsDrop.slice();
    }
  }else{
    IDX.itemsDropDisplay = IDX.itemsDrop.slice();
  }
  IDX.items = IDX.itemsAll.slice();
  IDX.monstersDrop = getMonsterNamesWithRealDrops();
  IDX.monstersAll = Array.isArray(DATA.all_monsters) ? DATA.all_monsters.map(x=>String(x||'').trim()).filter(Boolean) : IDX.monstersDrop.slice();
  IDX.monsters = IDX.monstersAll.slice();
  const maps = Array.isArray(DATA.maps)?DATA.maps:[];
  const seenMapCodes = {};
  function registerMapAlias(keyLike, canonicalCode, nameLike){
    const key0 = String(keyLike||'').trim();
    const code0 = String(canonicalCode||'').trim() || key0;
    const name0 = String(nameLike||'').trim();
    if(!key0 && !code0 && !name0) return null;
    let base =
      IDX.mapByKey[code0] || IDX.mapByKey[String(code0).toLowerCase()] || IDX.mapByKey[String(code0).toUpperCase()] ||
      IDX.mapByKey[key0] || IDX.mapByKey[String(key0).toLowerCase()] || IDX.mapByKey[String(key0).toUpperCase()] ||
      (name0 ? (IDX.mapByKey[name0] || IDX.mapByKey[String(name0).toLowerCase()] || IDX.mapByKey[String(name0).toUpperCase()]) : null) ||
      null;
    if(base && typeof base === 'object'){
      try{ if(code0 && !String(base.code||'').trim()) base.code = code0; }catch(e){}
      try{
        const oldName = String(base.name||'').trim();
        if(name0 && (!oldName || oldName === String(base.code||'').trim() || oldName.toLowerCase() === key0.toLowerCase())){
          base.name = name0;
        }
      }catch(e2){}
    }else{
      base = {code: code0 || key0 || name0, name: name0 || code0 || key0};
    }
    const aliases = [];
    [key0, code0, name0].forEach(v=>{
      const s = String(v||'').trim();
      if(!s) return;
      aliases.push(s);
      aliases.push(String(s).toLowerCase());
      aliases.push(String(s).toUpperCase());
    });
    aliases.forEach(a=>{
      if(a) IDX.mapByKey[a] = base;
    });
    const ckey = String(base.code||code0||key0||'').trim().toLowerCase();
    if(ckey) seenMapCodes[ckey] = true;
    return base;
  }
  function rebuildMapRowsFromAliases(){
    IDX.maps = [];
    const outSeenNames = {};
    Object.keys(seenMapCodes).forEach(ck=>{
      const mp = IDX.mapByKey[ck] || IDX.mapByKey[String(ck).toLowerCase()] || IDX.mapByKey[String(ck).toUpperCase()] || null;
      if(!mp) return;
      const code = String(mp.code||ck).trim() || ck;
      const name = String(mp.name||'').trim() || code;
      const nk = String(name||'').trim().toLowerCase();
      if(!nk || outSeenNames[nk]) return;
      outSeenNames[nk] = true;
      if(IDX.maps.length < 5000) IDX.maps.push({code:code, name:name});
    });
  }
  maps.forEach(mp=>{
    const code = String(mp.code||'').trim();
    const name = String(mp.name||'').trim() || code;
    const ck = String(code||'').trim().toLowerCase();
    if(ck) seenMapCodes[ck] = true;
    if(code){
      IDX.mapByKey[code]=mp;
      IDX.mapByKey[String(code).toLowerCase()] = mp;
      IDX.mapByKey[String(code).toUpperCase()] = mp;
    }
    if(name){
      IDX.mapByKey[name]=mp;
      IDX.mapByKey[String(name).toLowerCase()] = mp;
    }
  });
  const mapIndex = Array.isArray(DATA.map_index)?DATA.map_index:[];
  mapIndex.forEach(mi=>{
    const key0 = String(mi && (mi.key || mi.k) || '').trim();
    const code0 = String(mi && mi.code || '').trim();
    const name0 = String(mi && mi.name || '').trim();
    const code = code0 || key0 || name0;
    const name = name0 || code0 || code;
    if(!code) return;
    let base = IDX.mapByKey[code] || IDX.mapByKey[String(code).toLowerCase()] || IDX.mapByKey[String(code).toUpperCase()] || null;
    if(base && typeof base === 'object'){
      try{ if(!base.code) base.code = code; }catch(e){}
      if(name){ try{ base.name = name; }catch(e2){} }
    }else{
      base = {code:code, name:name||code};
    }
    IDX.mapByKey[code] = base;
    IDX.mapByKey[String(code).toLowerCase()] = base;
    IDX.mapByKey[String(code).toUpperCase()] = base;
    if(name){
      IDX.mapByKey[name] = base;
      IDX.mapByKey[String(name).toLowerCase()] = base;
    }
    if(key0){
      IDX.mapByKey[key0] = base;
      IDX.mapByKey[String(key0).toLowerCase()] = base;
      IDX.mapByKey[String(key0).toUpperCase()] = base;
    }
    seenMapCodes[String(code).toLowerCase()] = true;
  });
  const routes = Array.isArray(DATA.routes)?DATA.routes:[];
  routes.forEach(r=>{
    const f = String(r && r.from || '').trim();
    const t = String(r && r.to || '').trim();
    if(!f || !t) return;
    const fkey = resolveMapCode(f);
    const tkey = resolveMapCode(t);
    if(!fkey || !tkey) return;
    try{ r._fromKey = fkey; r._toKey = tkey; }catch(e){}
    registerMapAlias(f, fkey, String(r && (r.from_name || '') || '').trim());
    registerMapAlias(t, tkey, String(r && (r.to_name || '') || '').trim());
    if(!IDX.routesByFrom[fkey]) IDX.routesByFrom[fkey] = [];
    IDX.routesByFrom[fkey].push(r);
    IDX.routesByFrom[fkey.toLowerCase()] = IDX.routesByFrom[fkey];
    if(!IDX.routesByTo[tkey]) IDX.routesByTo[tkey] = [];
    IDX.routesByTo[tkey].push(r);
    IDX.routesByTo[tkey.toLowerCase()] = IDX.routesByTo[tkey];
  });

  const npcs = Array.isArray(DATA.npcs)?DATA.npcs:[];
  const npcEdgeSeen = {};
  npcs.forEach(loc=>{
    const npcName = String((loc && (loc.npc || loc.name)) || '').trim();
    const fromRaw = String((loc && (loc.map || loc.map_name)) || '').trim();
    const fromKey = resolveMapCode(fromRaw);
    if(!fromKey) return;
    registerMapAlias(fromRaw, fromKey, String((loc && loc.map_name) || '').trim());
    const fx = (loc && loc.x != null) ? loc.x : '';
    const fy = (loc && loc.y != null) ? loc.y : '';
    const tele = (loc && Array.isArray(loc.teleports)) ? loc.teleports : [];
    for(let i=0;i<tele.length;i++){

      const t = tele[i] || {};
      const toRaw = String(t.map||t.map_name||'').trim();
      const toKey = resolveMapCode(toRaw);
      if(!toKey) continue;
      registerMapAlias(toRaw, toKey, String(t.map_name||'').trim());
      const tx = (t.x != null) ? t.x : '';
      const ty = (t.y != null) ? t.y : '';
      const rr = (t.r != null && t.r !== '') ? t.r : '';
      const randomTo = !!(t && (t.random_to || t.randomTo));
      const sig = String(fromKey).toLowerCase()+'>'+String(toKey).toLowerCase()+'|'+String(fx)+'|'+String(fy)+'|'+String(tx)+'|'+String(ty)+'|'+npcName+'|'+String(rr);
      if(npcEdgeSeen[sig]) continue;
      npcEdgeSeen[sig] = 1;
      const r = {
        from: fromKey,
        to: toKey,
        from_x: fx,
        from_y: fy,
        to_x: tx,
        to_y: ty,
        via: 'npc',
        npc: npcName,
        r: rr,
        random_to: randomTo
      };
      try{ r._fromKey = fromKey; r._toKey = toKey; }catch(e){}
      try{ r.from_name = mapLabel(fromKey) || fromRaw || fromKey; }catch(e2){}
      try{ r.to_name = mapLabel(toKey) || String(t.map_name||'').trim() || toRaw || toKey; }catch(e3){}
      if(!IDX.routesByFrom[fromKey]) IDX.routesByFrom[fromKey] = [];
      IDX.routesByFrom[fromKey].push(r);
      IDX.routesByFrom[fromKey.toLowerCase()] = IDX.routesByFrom[fromKey];
      if(!IDX.routesByTo[toKey]) IDX.routesByTo[toKey] = [];
      IDX.routesByTo[toKey].push(r);
      IDX.routesByTo[toKey.toLowerCase()] = IDX.routesByTo[toKey];
      if(!IDX.npcRoutesByTo[toKey]) IDX.npcRoutesByTo[toKey] = [];
      IDX.npcRoutesByTo[toKey].push(r);
      IDX.npcRoutesByTo[toKey.toLowerCase()] = IDX.npcRoutesByTo[toKey];
      if(toRaw){
        const tk = String(toRaw).trim();
        if(tk){
          IDX.npcRoutesByTo[tk] = IDX.npcRoutesByTo[toKey];
          IDX.npcRoutesByTo[tk.toLowerCase()] = IDX.npcRoutesByTo[toKey];
        }
      }
    }
  });
  npcs.forEach(n=>{
    const nm = String((n && (n.npc || n.name)) || '').trim();
    if(!nm) return;
    if(!IDX.npcByName[nm]){ IDX.npcByName[nm] = []; IDX.npcs.push(nm); }
    IDX.npcByName[nm].push(n);
  });
  rebuildMapRowsFromAliases();
  try{
    const rootNames = [
      '盟重土城','盟重省','盟重','比奇城','比奇省','比奇',
      '苍月岛','白日门','封魔谷','沙巴克','土城'
    ];
    const roots = [];
    for(let i=0;i<rootNames.length;i++){
      const k = resolveMapCode(rootNames[i]);
      if(!k) continue;
      if(roots.indexOf(k) >= 0) continue;
      const hasEdges = (IDX.routesByFrom[k] && IDX.routesByFrom[k].length) || (IDX.routesByTo[k] && IDX.routesByTo[k].length) || (IDX.routesByFrom[String(k).toLowerCase()] && IDX.routesByFrom[String(k).toLowerCase()].length) || (IDX.routesByTo[String(k).toLowerCase()] && IDX.routesByTo[String(k).toLowerCase()].length);
      if(hasEdges) roots.push(k);
    }
    IDX._routeRoots = roots;
  }catch(e2){}
  rebuildPrimaryRows();
}

function mapMonsterGroups(selMap){
  const code = resolveMapCode(selMap);
  if(!code) return [];
  if(VIEW_CACHE.mapMonsters[code]) return VIEW_CACHE.mapMonsters[code];
  const grouped = {};
  const order = [];
  const allMons = Array.isArray(IDX.monstersAll) && IDX.monstersAll.length ? IDX.monstersAll : Object.keys(IDX.monByName || {});
  for(let i=0;i<allMons.length;i++){
    const monName = String(allMons[i] || '').trim();
    if(!monName) continue;
    const mon = IDX.monByName[monName];
    const sp = mon && Array.isArray(mon.spawns) ? mon.spawns.slice() : [];
    for(let j=0;j<sp.length;j++){
      const s = sp[j] || {};
      const raw = String((s && (s.map||s.map_code)) || '').trim() || String((s && (s.map_name||s.map)) || '').trim();
      const scode = resolveMapCode(raw);
      if(!scode || scode !== code) continue;
      if(!grouped[monName]){
        grouped[monName] = {name:monName, total:0, minTime:null, minTimeText:null, sample:[]};
        order.push(monName);
      }
      const g = grouped[monName];
      g.total += Number(s.count||0);
      const ttext = String((s && (s.time_text||s.timeText)) || '').trim();
      if(ttext){
        if(!g.minTimeText) g.minTimeText = ttext;
      }else if(!g.minTimeText){
        const tv = Number(s.time||0);
        if(g.minTime == null) g.minTime = tv;
        else if(tv > 0 && (g.minTime === 0 || tv < g.minTime)) g.minTime = tv;
      }
      const cx = (s.x != null) ? s.x : '';
      const cy = (s.y != null) ? s.y : '';
      if(g.sample.length < 3 && cx !== '' && cy !== '') g.sample.push(String(cx)+','+String(cy));
    }
  }
  const rows = order.map((nm,i)=>{
    const g = grouped[nm] || {};
    let sub = '';
    if(g.sample && g.sample.length){
      sub = '坐标 ' + g.sample.join(' ') + (g.sample.length >= 3 ? ' ...' : '');
    }
    const right = g.minTimeText ? (String(g.minTimeText) + '/' + Number(g.total||0) + '只') : ((Number(g.minTime||0))+'分/'+Number(g.total||0)+'只');
    return {key:nm, badge:i+1, title:nm, sub:sub, right:right};
  });
  VIEW_CACHE.mapMonsters[code] = rows;
  return rows;
}

function setHeaders(){
  if(STATE.tab==='item'){
    el('h1').textContent='物品名称';
    el('h2').textContent='物品出处';
    el('h3').textContent='刷新地图';
    el('h4').textContent='地图走法';
  }else if(STATE.tab==='monster'){
    el('h1').textContent='怪物名称';
    el('h2').textContent='掉落物品';
    el('h3').textContent='刷新地图';
    el('h4').textContent='地图走法';
  }else if(STATE.tab==='map'){
    el('h1').textContent='地图名称';
    el('h2').textContent='地图走法';
    el('h3').textContent='刷新怪物';
    el('h4').textContent='掉落物品';
  }else if(STATE.tab==='npc'){
    el('h1').textContent='NPC名称';
    el('h2').textContent='所在位置';
    el('h3').textContent='地图走法';
    el('h4').textContent='相关物品';
  }
}

/* 重置分页并回到顶部，确保筛选或切换后从第一页开始浏览。 */
function resetPages(ids){
  const arr = (Array.isArray(ids) && ids.length) ? ids : ['l1','l2','l3','l4'];
  for(let i=0;i<arr.length;i++){
    const id = String(arr[i] || '').trim();
    if(!id) continue;
    PAGE_STATE[id] = 1;
    try{ const node = el(id); if(node) node.scrollTop = 0; }catch(e){}
  }
}

/* 根据列表编号定位对应分页栏。 */
function pagerIdByList(listId){
  const m = String(listId || '').match(/^l([1-4])$/);
  return m ? ('p' + m[1]) : '';
}

/* 根据列表编号定位列头统计文本节点。 */
function headerStatIdByList(listId){
  const m = String(listId || '').match(/^l([1-4])$/);
  return m ? ('h' + m[1] + 's') : '';
}

function listUnitByContext(listId){
  const id = String(listId || '').trim();
  const tab = String((STATE && STATE.tab) || '').trim();
  if(id === 'l1'){
    if(tab === 'item') return '项';
    if(tab === 'monster') return '只';
    if(tab === 'map') return '张';
    if(tab === 'npc') return '个';
  }
  if(id === 'l2'){
    if(tab === 'item') return '处';
    if(tab === 'monster') return '项';
    if(tab === 'map') return '条';
    if(tab === 'npc') return '处';
  }
  if(id === 'l3'){
    if(tab === 'item') return '张';
    if(tab === 'monster') return '张';
    if(tab === 'map') return '只';
    if(tab === 'npc') return '条';
  }
  if(id === 'l4'){
    if(tab === 'item') return '条';
    if(tab === 'monster') return '条';
    if(tab === 'map') return '项';
    if(tab === 'npc') return '项';
  }
  return '项';
}

/* 列头只显示当前勾选状态下的真实总数。 */
function setListHeaderStat(listId, total){
  const sid = headerStatIdByList(listId);
  const node = sid ? el(sid) : null;
  if(!node) return;
  const totalNum = Math.max(0, Number(total || 0) || 0);
  if(totalNum <= 0){
    node.textContent = '';
    return;
  }
  node.textContent = '总数 ' + totalNum + ' ' + listUnitByContext(listId);
}

/* 清空单个列表的分页栏。 */
function clearPager(listId){

  const pid = pagerIdByList(listId);
  const node = pid ? el(pid) : null;
  if(!node) return;
  node.innerHTML = '';
  node.classList.add('hidden');
}

/* 切换到首页或加载中状态时清空全部分页栏。 */
function clearAllPagers(){
  clearPager('l1');
  clearPager('l2');
  clearPager('l3');
  clearPager('l4');
}

/* 约束当前页码，避免筛选后页码越界。 */
function syncPage(listId, total, pageSize){
  const size = Math.max(1, Number(pageSize || 1) || 1);
  const maxPage = Math.max(1, Math.ceil(Number(total || 0) / size));
  let page = Number(PAGE_STATE[listId] || 1) || 1;
  if(page < 1) page = 1;
  if(page > maxPage) page = maxPage;
  PAGE_STATE[listId] = page;
  return page;
}

/* 生成单行 HTML，供普通渲染和虚拟滚动复用。 */
function renderRowHtml(r, activeKey){
  const row = r || {};
  const k = String(row.key || '');
  const leftBadge = (row.badge!=null)?('<div class="badge">'+esc(row.badge)+'</div>'):'';
  const right = (row.right!=null)?('<div class="right">'+esc(row.right)+'</div>'):'';
  const sub = row.sub?('<div class="sub">'+esc(row.sub)+'</div>'):'';
  const cls = (k && k===activeKey)?'row active':'row';
  return '<div class="'+cls+'" data-key="'+esc(k)+'">'
    + '<div class="left">'+leftBadge+'<div style="min-width:0"><div class="title">'+esc(row.title)+'</div>'+sub+'</div></div>'
    + right
    + '</div>';
}

/* 根据当前滚动位置，仅渲染可视区附近的行，降低大列表 DOM 数量。 */
function renderVirtualViewport(node){
  const meta = node && node._vmeta ? node._vmeta : null;
  if(!meta){
    if(node) node.innerHTML = '<div class="empty">暂无数据</div>';
    return;
  }
  const rows = Array.isArray(meta.rows) ? meta.rows : [];
  if(!rows.length){
    node.innerHTML = '<div class="empty">暂无数据</div>';
    return;
  }
  const viewport = Math.max(node.clientHeight || 520, VLIST_ROW_HEIGHT);
  const scrollTop = Math.max(0, node.scrollTop || 0);
  const visible = Math.ceil(viewport / VLIST_ROW_HEIGHT) + VLIST_BUFFER * 2;
  const start = Math.max(0, Math.floor(scrollTop / VLIST_ROW_HEIGHT) - VLIST_BUFFER);
  const end = Math.min(rows.length, start + visible);
  if(meta.start === start && meta.end === end && meta.activeKey === meta._activeRendered){
    return;
  }
  meta.start = start;
  meta.end = end;
  meta._activeRendered = meta.activeKey;
  const topPad = start * VLIST_ROW_HEIGHT;
  const bottomPad = Math.max(0, (rows.length - end) * VLIST_ROW_HEIGHT);
  let html = '';
  if(topPad > 0) html += '<div class="vpad" style="height:' + topPad + 'px"></div>';
  for(let i=start;i<end;i++){
    html += renderRowHtml(rows[i], meta.activeKey);
  }
  if(bottomPad > 0) html += '<div class="vpad" style="height:' + bottomPad + 'px"></div>';
  node.innerHTML = html;
}

/* 自动续载模式下不显示底部状态栏或翻页控件。 */
function renderPager(listId, total, pageSize, page){
  clearPager(listId);
}


/* 滑动接近底部时自动追加下一页，替代手动点击翻页。 */
function tryAutoLoadNextPage(node){
  const meta = node && node._pageMeta ? node._pageMeta : null;
  if(!node || !meta) return;
  const listId = String(meta.listId || '').trim();
  if(!listId || node._autoPagingBusy) return;
  const total = Math.max(0, Number(meta.total || 0) || 0);
  const size = Math.max(1, Number(meta.pageSize || PAGE_SIZE_DEFAULT) || PAGE_SIZE_DEFAULT);
  const maxPage = Math.max(1, Math.ceil(total / size));
  const page = Number(PAGE_STATE[listId] || 1) || 1;
  if(page >= maxPage) return;
  const remain = Number(node.scrollHeight || 0) - Number(node.clientHeight || 0) - Number(node.scrollTop || 0);
  if(remain > AUTO_PAGE_TRIGGER_GAP) return;
  node._autoPagingBusy = true;
  PAGE_STATE[listId] = page + 1;
  node._keepScrollOnAppend = true;
  const top = Number(node.scrollTop || 0) || 0;
  try{ render(); }finally{
    try{ node.scrollTop = top; }catch(e){}
    setTimeout(function(){ try{ node._autoPagingBusy = false; }catch(e2){} }, 0);
  }
}

/* 普通列表改为“滑动自动续载 + 当前已加载范围虚拟滚动”。 */
function renderList(node, rows, activeKey, pageSize){
  const listId = String(node && node.id || '').trim();
  const size = Math.max(1, Number(pageSize || PAGE_SIZE_DEFAULT) || PAGE_SIZE_DEFAULT);
  if(!rows || !rows.length){
    node.innerHTML = '<div class="empty">暂无数据</div>';
    node._vmeta = null;
    node._pageMeta = null;
    setListHeaderStat(listId, 0);
    clearPager(listId);
    return;
  }
  const page = syncPage(listId, rows.length, size);
  const loadedRows = rows.slice(0, page * size);
  const prevPage = Number(node.getAttribute('data-page') || 0) || 0;
  const keepScroll = !!node._keepScrollOnAppend;
  node._keepScrollOnAppend = false;
  node.setAttribute('data-page', String(page));
  node._pageMeta = {listId:listId, total:rows.length, pageSize:size, loaded:loadedRows.length};
  node._vmeta = {rows:loadedRows, activeKey:activeKey || '', start:-1, end:-1, _activeRendered:null};
  setListHeaderStat(listId, rows.length);

  if(prevPage !== page && !keepScroll){
    try{ node.scrollTop = 0; }catch(e){}
  }
  renderVirtualViewport(node);
  renderPager(listId, rows.length, size, page);
}


function bindClicks(){
  if(_LIST_CLICK_BOUND) return;
  _LIST_CLICK_BOUND = true;
  const ids = ['l1','l2','l3','l4'];
  ids.forEach((id, idx)=>{
    const node = el(id);
    if(!node) return;
    node.onclick = function(ev){
      let t = ev && ev.target ? ev.target : null;
      while(t && t !== node && !(t.classList && t.classList.contains('row'))){
        t = t.parentNode;
      }
      if(!t || t === node) return;
      const k = t.getAttribute('data-key') || '';
      if(idx===0){ STATE.sel1=k; STATE.sel2=''; STATE.sel3=''; STATE.sel4=''; resetPages(['l2','l3','l4']); }
      if(idx===1){ STATE.sel2=k; STATE.sel3=''; STATE.sel4=''; resetPages(['l3','l4']); }
      if(idx===2){ STATE.sel3=k; STATE.sel4=''; resetPages(['l4']); }
      if(idx===3){ STATE.sel4=k; }
      render();
    };
  });
}

function bindAutoPageScroll(){
  if(_AUTO_PAGE_SCROLL_BOUND) return;
  _AUTO_PAGE_SCROLL_BOUND = true;
  const ids = ['l1','l2','l3','l4'];
  ids.forEach(id=>{
    const node = el(id);
    if(!node) return;
    node.addEventListener('scroll', function(){
      if(node._vmeta) scheduleVirtualViewport(node);
      tryAutoLoadNextPage(node);
    }, {passive:true});
  });
}




function filterByKw(list, kwRaw){
  const kw=String(kwRaw||'').trim().toLowerCase();
  if(!kw) return list.slice();
  const tokens = kw.split(/\s+/).filter(Boolean);
  if(!tokens.length) return list.slice();
  return list.filter(x=>{
    const t = String(x||'').toLowerCase();
    for(let i=0;i<tokens.length;i++){
      const ok = t.indexOf(tokens[i]) >= 0;
      if(!ok) return false;
    }
    return true;
  });
}

function filterRowsByKw(rows, kwRaw){
  const kw = String(kwRaw||'').trim().toLowerCase();
  if(!kw) return rows.slice();
  return rows.filter(r=>{
    const t = (String((r && r.title) || '') + ' ' + String((r && r.sub) || '') + ' ' + String((r && r.right) || '')).toLowerCase();
    return t.indexOf(kw) >= 0;
  });
}

function _sortName(a, b){
  return String(a||'').localeCompare(String(b||''), 'zh');
}

function applySortItems(list){
  const out = list.slice();
  if(STATE.sort === 'name'){
    out.sort(_sortName);
    return out;
  }
  if(STATE.sort === 'rate'){
    out.sort((a,b)=>{
      const da = Number((IDX.itemMinDen && IDX.itemMinDen[a]) || 1e18);
      const db = Number((IDX.itemMinDen && IDX.itemMinDen[b]) || 1e18);
      return da - db;
    });
    return out;
  }
  return out;
}

function applySortNames(list){
  const out = list.slice();
  if(STATE.sort === 'name'){
    out.sort(_sortName);
  }
  return out;
}

function render(){
  setHeaders();
  el('h1s').textContent=''; el('h2s').textContent=''; el('h3s').textContent=''; el('h4s').textContent='';
  if(STATE.tab==='home'){ setView('home'); renderHome(); return; }
  setView('main');
  if(!DATA){ el('l1').innerHTML='<div class="empty">数据未加载</div>'; el('l2').innerHTML=''; el('l3').innerHTML=''; el('l4').innerHTML=''; return; }

  if(STATE.tab==='item'){
    const baseItems = STATE.showAll ? (IDX.itemsAll || IDX.items || []) : (IDX.itemsDropDisplay || IDX.itemsDrop || IDX.items || []);
    let items = filterByKw(baseItems, STATE.kw1);
    items = applySortItems(items);
    el('h1s').textContent = '总数 ' + items.length + ' 项';
    renderList(el('l1'), items.map((n,i)=>({key:n, badge:i+1, title:n})), STATE.sel1);

    const drops = (STATE.sel1 && IDX.itemDrops[STATE.sel1]) ? IDX.itemDrops[STATE.sel1].slice() : [];
    drops.sort((a,b)=>Number(a.den||0)-Number(b.den||0));
    const d2 = filterRowsByKw(drops.map((d,i)=>({key:d.monster, badge:i+1, title:d.monster, right:(STATE.showRate ? ('1/'+d.den) : '')})), STATE.kw2);
    el('h2s').textContent = STATE.sel1 ? ('总数 ' + d2.length+' 个') : '';
    renderList(el('l2'), d2, STATE.sel2);

    const mon = STATE.sel2 ? IDX.monByName[STATE.sel2] : null;
    const sp = mon && Array.isArray(mon.spawns) ? mon.spawns.slice() : [];
    const grouped = {};
    const order = [];
    for(let i=0;i<sp.length;i++){
      const s = sp[i] || {};
      const raw = String((s && (s.map||s.map_code)) || '').trim() || String((s && (s.map_name||s.map)) || '').trim();
      const code = resolveMapCode(raw);
      if(!code) continue;
      if(!grouped[code]){
        const nm = String((s && s.map_name) || '').trim();
        grouped[code] = {code:code, title:(mapLabel(code) || nm || raw || code), points:0, total:0, minTime:null, minTimeText:null, sample:[]};
        order.push(code);
      }
      const g = grouped[code];
      g.points += 1;
      const cx = Number(s.x||0), cy = Number(s.y||0);
      if(g.sample.length < 3) g.sample.push(String(cx)+','+String(cy));
      g.total += Number(s.count||0);
      const ttext = String((s && (s.time_text||s.timeText)) || '').trim();
      if(ttext){
        if(!g.minTimeText) g.minTimeText = ttext;
      }else if(!g.minTimeText){
        const tv = Number(s.time||0);
        if(g.minTime == null) g.minTime = tv;
        else if(tv > 0 && (g.minTime === 0 || tv < g.minTime)) g.minTime = tv;
      }
    }
    const s3 = filterRowsByKw(order.map((code,i)=>{
      const g = grouped[code] || {};
      let sub = '点数 ' + Number(g.points||0);
      if(g.sample && g.sample.length){
        sub += ' | 坐标 ' + g.sample.join(' ') + (Number(g.points||0) > g.sample.length ? ' ...' : '');
      }
      if(g.code && g.title && g.title !== g.code) sub += ' | ' + g.code;
      const right = g.minTimeText ? (String(g.minTimeText) + '/' + Number(g.total||0) + '只') : ((Number(g.minTime||0))+'分/'+Number(g.total||0)+'只');
      return {key:g.code, badge:i+1, title:g.title||g.code, sub:sub, right:right};
    }), STATE.kw3);
    el('h3s').textContent = STATE.sel2 ? ('总数 ' + s3.length+' 张') : '';
    renderList(el('l3'), s3, STATE.sel3);

    if(!STATE.sel3){ el('l4').innerHTML='<div class="empty">选择刷新地图后显示走法</div>'; }
    else{
      const chains = routeChainsToMapCached(STATE.sel3);
      const npcDirect = directNpcRoutesToMap(STATE.sel3).map(r=>[r]);
      if(chains && chains.length){
        const chainsAll = mergeRouteChains(chains, npcDirect);
        el('h4s').textContent = '总数 ' + chainsAll.length + ' 条';
        renderRouteMethods(el('l4'), chainsAll);
      }else{
        const rts = mergeRouteEdges(directRoutesToMapCached(STATE.sel3), directNpcRoutesToMap(STATE.sel3));
        el('h4s').textContent = rts.length ? (rts.length + ' 条') : '';
        if(!rts.length){ el('l4').innerHTML='<div class="empty">暂无地图走法数据</div>'; }
        else{
          const rows = rts.map((r,i)=>{
            const from = String(r && r.from || '').trim();
            const to = String(r && r.to || '').trim();
            const fromName = String(r && (r.from_name || '') || '').trim() || mapLabel(from) || from;
            const toName = String(r && (r.to_name || '') || '').trim() || mapLabel(to) || to;
            const sub = routeStepText(r);
            return {key:'in#'+from+'#'+i, badge:i+1, title:fromName||toName, sub:sub, right:resolveMapCode(from)};
          });
          renderList(el('l4'), rows, STATE.sel4);
        }
      }
    }
  } else if(STATE.tab==='monster'){
    let baseMons = (IDX.monstersAll && IDX.monstersAll.length ? IDX.monstersAll : IDX.monsters);
    if(!STATE.showAll){
      baseMons = getMonsterNamesWithRealDrops();
    }
    let mons = applySortNames(filterByKw(baseMons, STATE.kw1));
    if(STATE.sel1 && mons.indexOf(STATE.sel1) < 0){
      STATE.sel1=''; STATE.sel2=''; STATE.sel3=''; STATE.sel4='';
    }
    el('h1s').textContent = '总数 ' + mons.length + ' 只';
    renderList(el('l1'), mons.map((n,i)=>({key:n, badge:i+1, title:n})), STATE.sel1);
    const mon = STATE.sel1 ? IDX.monByName[STATE.sel1] : null;
    const its = getStrictRealMonsterDrops(mon).slice();
    its.sort((a,b)=>itemOverallDen(a)-itemOverallDen(b));
    const l2 = filterRowsByKw(its.map((it,i)=>({key:it.name, badge:i+1, title:it.name, right:(STATE.showRate ? ('1/'+itemOverallDen(it)) : '')})), STATE.kw2);
    el('h2s').textContent = STATE.sel1 ? ('总数 ' + l2.length+' 件') : '';
    renderList(el('l2'), l2, STATE.sel2);
    const sp = mon && Array.isArray(mon.spawns) ? mon.spawns.slice() : [];
    const grouped = {};
    const order = [];
    for(let i=0;i<sp.length;i++){
      const s = sp[i] || {};
      const raw = String((s && (s.map||s.map_code)) || '').trim() || String((s && (s.map_name||s.map)) || '').trim();
      const code = resolveMapCode(raw);
      if(!code) continue;
      if(!grouped[code]){
        const nm = String((s && s.map_name) || '').trim();
        grouped[code] = {code:code, title:(mapLabel(code) || nm || raw || code), points:0, total:0, minTime:null, minTimeText:null, sample:[]};
        order.push(code);
      }
      const g = grouped[code];
      g.points += 1;
      const cx = Number(s.x||0), cy = Number(s.y||0);
      if(g.sample.length < 3) g.sample.push(String(cx)+','+String(cy));
      g.total += Number(s.count||0);
      const ttext = String((s && (s.time_text||s.timeText)) || '').trim();
      if(ttext){
        if(!g.minTimeText) g.minTimeText = ttext;
      }else if(!g.minTimeText){
        const tv = Number(s.time||0);
        if(g.minTime == null) g.minTime = tv;
        else if(tv > 0 && (g.minTime === 0 || tv < g.minTime)) g.minTime = tv;
      }
    }
    const s3 = filterRowsByKw(order.map((code,i)=>{
      const g = grouped[code] || {};
      let sub = '点数 ' + Number(g.points||0);
      if(g.sample && g.sample.length){
        sub += ' | 坐标 ' + g.sample.join(' ') + (Number(g.points||0) > g.sample.length ? ' ...' : '');
      }
      if(g.code && g.title && g.title !== g.code) sub += ' | ' + g.code;
      const right = g.minTimeText ? (String(g.minTimeText) + '/' + Number(g.total||0) + '只') : ((Number(g.minTime||0))+'分/'+Number(g.total||0)+'只');
      return {key:g.code, badge:i+1, title:g.title||g.code, sub:sub, right:right};
    }), STATE.kw3);
    el('h3s').textContent = STATE.sel1 ? ('总数 ' + s3.length+' 张') : '';
    renderList(el('l3'), s3, STATE.sel3);
    if(!STATE.sel3){ el('l4').innerHTML='<div class="empty">选择刷新地图后显示走法</div>'; }
    else{
      const chains = routeChainsToMapCached(STATE.sel3);
      const npcDirect = directNpcRoutesToMap(STATE.sel3).map(r=>[r]);
      if(chains && chains.length){
        const chainsAll = mergeRouteChains(chains, npcDirect);
        el('h4s').textContent = '总数 ' + chainsAll.length + ' 条';
        renderRouteMethods(el('l4'), chainsAll);
      }else{
        const rts = mergeRouteEdges(directRoutesToMapCached(STATE.sel3), directNpcRoutesToMap(STATE.sel3));
        el('h4s').textContent = rts.length ? (rts.length + ' 条') : '';
        if(!rts.length){ el('l4').innerHTML='<div class="empty">暂无地图走法数据</div>'; }
        else{
          const rows = rts.map((r,i)=>{
            const from = String(r && r.from || '').trim();
            const to = String(r && r.to || '').trim();
            const fromName = String(r && (r.from_name || '') || '').trim() || mapLabel(from) || from;
            const toName = String(r && (r.to_name || '') || '').trim() || mapLabel(to) || to;
            const sub = routeStepText(r);
            return {key:'in#'+from+'#'+i, badge:i+1, title:fromName||toName, sub:sub, right:resolveMapCode(from)};
          });
          renderList(el('l4'), rows, STATE.sel4);
        }
      }
    }
  } else if(STATE.tab==='map'){
    let mapNames = IDX.maps.map(x=>x.name);
    if(!STATE.showAll){
      mapNames = mapNames.filter(n=>{
        try{ return mapMonsterGroups(n).length > 0; }catch(e){ return false; }
      });
    }
    let maps = applySortNames(filterByKw(mapNames, STATE.kw1));
    el('h1s').textContent = '总数 ' + maps.length + ' 张';
    renderList(el('l1'), maps.map((n,i)=>({key:n, badge:i+1, title:n})), STATE.sel1);
    if(!STATE.sel1){ el('l2').innerHTML='<div class="empty">选择地图后显示走法/相关信息</div>'; }
    else{
      const chains = routeChainsToMapCached(STATE.sel1);
      const npcDirect = directNpcRoutesToMap(STATE.sel1).map(r=>[r]);
      if(chains && chains.length){
        const chainsAll = mergeRouteChains(chains, npcDirect);
        el('h2s').textContent = '总数 ' + chainsAll.length + ' 条';
        renderRouteMethods(el('l2'), chainsAll);
      }else{
        const rts = mergeRouteEdges(directRoutesToMapCached(STATE.sel1), directNpcRoutesToMap(STATE.sel1));
        el('h2s').textContent = rts.length ? (rts.length + ' 条') : '';
        if(!rts.length){ el('l2').innerHTML='<div class="empty">暂无地图走法数据</div>'; }
        else{
          const rows = filterRowsByKw(rts.map((r,i)=>{
            const from = String(r && r.from || '').trim();
            const to = String(r && r.to || '').trim();
            const fromName = String(r && (r.from_name || '') || '').trim() || mapLabel(from) || from;
            const toName = String(r && (r.to_name || '') || '').trim() || mapLabel(to) || to;
            const sub = routeStepText(r);
            return {key:'in#'+from+'#'+i, badge:i+1, title:fromName||toName, sub:sub, right:resolveMapCode(from)};
          }), STATE.kw2);
          renderList(el('l2'), rows, STATE.sel2);
        }
      }
    }
    const baseMapMonsters = STATE.sel1 ? mapMonsterGroups(STATE.sel1) : [];
    let rows3 = baseMapMonsters.slice();
    if(!STATE.showAll){
      const realMonSet = new Set(getMonsterNamesWithRealDrops());
      rows3 = rows3.filter(r=>realMonSet.has(String(r && r.key || '').trim()));
    }
    if(STATE.sel3 && rows3.findIndex(r=>String(r && r.key || '').trim()===String(STATE.sel3||'').trim()) < 0){
      STATE.sel3=''; STATE.sel4='';
    }
    const l3 = filterRowsByKw(rows3, STATE.kw3);
    el('h3s').textContent = STATE.sel1 ? ('总数 ' + l3.length+' 只') : '';
    renderList(el('l3'), l3, STATE.sel3);
    if(!STATE.sel3){
      el('h4s').textContent = '';
      el('l4').innerHTML = '<div class="empty">?????????????</div>';
    }else{
      const mon = getMonsterByName(STATE.sel3);
      const its = getStrictRealMonsterDrops(mon).slice();
      its.sort((a,b)=>itemOverallDen(a)-itemOverallDen(b));
      const l4 = filterRowsByKw(its.map((it,i)=>({key:it.name, badge:i+1, title:it.name, right:(STATE.showRate ? ('1/'+itemOverallDen(it)) : '')})), STATE.kw4);
      el('h4s').textContent = l4.length ? ('?? ' + l4.length+' ?') : '';
      if(!l4.length){
        el('l4').innerHTML = '<div class="empty">?????????</div>';
      }else{
        renderList(el('l4'), l4, STATE.sel4);
      }
    }

  } else if(STATE.tab==='npc'){
    let npcs = applySortNames(filterByKw(IDX.npcs, STATE.kw1));
    el('h1s').textContent = npcs.length ? ('总数 ' + npcs.length + ' 个') : '';
    renderList(el('l1'), npcs.map((n,i)=>({key:n, badge:i+1, title:n})), STATE.sel1);

    const locs = STATE.sel1 ? (IDX.npcByName[STATE.sel1]||[]).slice() : [];
    const locByKey = {};
    const s2 = filterRowsByKw(locs.map((n,i)=>{
      const map = String((n && n.map) || '').trim() || String((n && n.map_name) || '').trim();
      const code = resolveMapCode(map);
      const title = mapLabel(code) || String((n && n.map_name) || '').trim() || code;
      const x = (n && n.x != null) ? n.x : '';
      const y = (n && n.y != null) ? n.y : '';
      const key = code + '|' + x + '|' + y + '|' + i;
      locByKey[key] = n;
      let sub = (x!=='' && y!=='') ? ('坐标 ' + x + ',' + y) : '';
      if(code && title && title !== code) sub += (sub ? ' | ' : '') + code;
      return {key:key, badge:i+1, title:title||code, sub:sub, right:''};
    }), STATE.kw2);
    el('h2s').textContent = STATE.sel1 ? ('总数 ' + s2.length + ' 处') : '';
    renderList(el('l2'), s2, STATE.sel2);

    const selLoc = (STATE.sel2 && locByKey[STATE.sel2]) ? locByKey[STATE.sel2] : null;
    const selMap = selLoc ? (String(selLoc.map||'').trim() || String(selLoc.map_name||'').trim()) : '';
    if(!selMap){
      el('l3').innerHTML='<div class="empty">选择所在位置后显示走法</div>';
      el('l4').innerHTML='<div class="empty">选择所在位置后显示相关物品</div>';
    }else{
      const chains = routeChainsToMapCached(selMap);
      const tele = selLoc && Array.isArray(selLoc.teleports) ? selLoc.teleports.slice() : [];
      const rows = [];
      if(chains && chains.length){
        for(let i=0;i<chains.length;i++){
          const p = chains[i] || [];
          const first = (p && p.length) ? (p[0]||{}) : {};
          const startKey = String(first._fromKey || first.from || '').trim();
          const startName = String(first.from_name||'').trim() || mapLabel(startKey) || startKey || ('路线'+(i+1));
          const sub = formatRouteChain(p);
          rows.push({key:'mi#p#'+startKey+'#'+i, badge:rows.length+1, title:startName, sub:sub, right:String(p.length||0)+'段'});
        }
      }
      if(tele && tele.length){
        const fm = resolveMapCode(selMap);
        const fmName = mapLabel(fm) || selMap;
        const fmx = (selLoc && selLoc.x != null) ? selLoc.x : '';
        const fmy = (selLoc && selLoc.y != null) ? selLoc.y : '';
        const npcName = (selLoc && selLoc.npc) ? selLoc.npc : '';
        for(let i=0;i<tele.length;i++){
          const t = tele[i] || {};
          const mp = String(t.map||'').trim();
          const code = resolveMapCode(mp);
          const title = mapLabel(code) || String(t.map_name||'').trim() || mp || code;
          const x = (t.x != null) ? t.x : '';
          const y = (t.y != null) ? t.y : '';
          const rr = (t.r != null && t.r !== '') ? t.r : '';
          const randomTo = !!(t && (t.random_to || t.randomTo));
          let sub = formatMoveSub(fmName, fmx, fmy, title, x, y, randomTo);
          sub += ' | NPC传送';
          if(npcName) sub += ' [' + npcName + ']';
          if(rr!=='') sub += ' 范围' + rr;
          rows.push({key:'tp#'+code+'#'+i, badge:rows.length+1, title:title||code, sub:sub, right:code||mp});
        }
      }
      const rows2 = filterRowsByKw(dedupeDisplayRows(rows), STATE.kw3);
      el('h3s').textContent = rows2.length ? ('总数 ' + rows2.length + ' 条') : '';
      if(!rows.length){ el('l3').innerHTML='<div class="empty">暂无地图走法数据</div>'; }
      else{ renderList(el('l3'), rows2, STATE.sel3); }

      const take = selLoc && Array.isArray(selLoc.take) ? selLoc.take.slice() : [];
      const give = selLoc && Array.isArray(selLoc.give) ? selLoc.give.slice() : [];
      const items = [];
      for(let i=0;i<take.length;i++){
        const it = take[i] || {};
        const nm = String(it.name||'').trim(); if(!nm) continue;
        const cnt = Number(it.count||1) || 1;
        items.push({key:'take#'+nm+'#'+i, badge:items.length+1, title:nm, sub:'消耗', right:'x'+cnt});
      }
      for(let i=0;i<give.length;i++){
        const it = give[i] || {};
        const nm = String(it.name||'').trim(); if(!nm) continue;
        const cnt = Number(it.count||1) || 1;
        items.push({key:'give#'+nm+'#'+i, badge:items.length+1, title:nm, sub:'给予', right:'x'+cnt});
      }
      const items2 = filterRowsByKw(items, STATE.kw4);
      el('h4s').textContent = items2.length ? ('总数 ' + items2.length + ' 项') : '';
      if(!items2.length){
        el('l4').innerHTML='<div class="empty">暂无相关物品</div>';
      }else{
        renderList(el('l4'), items2, STATE.sel4);
      }
    }
  }
  bindClicks();
  bindAutoPageScroll();
}

function setVersion(q){
  CURRENT=q||null;
  DATA=null;
  resetViewCache();
  resetPages();
  STATE.sel1=''; STATE.sel2=''; STATE.sel3=''; STATE.sel4='';

  STATE.showRate = (q && q.show_rate === false) ? false : true;
  if(!q){ el('verInfo').textContent='选择查询版本'; el('guideBtn').classList.add('disabled'); el('guideBtn').href='#'; return; }
  el('verInfo').textContent = String(q.name||'').trim() || '已选择版本';
  const g = String(q.guide||'').trim();
  if(g){ el('guideBtn').href=g; el('guideBtn').classList.remove('disabled'); } else { el('guideBtn').classList.add('disabled'); el('guideBtn').href='#'; }
}

async function loadDataFor(q, force){
  if(!q){ DATA=null; resetViewCache(); _DETAIL_LOADED=false; _DETAIL_LOADING=null; render(); return; }
  const file = String(q.data_file||'droprate.json').trim();
  DATA=null;
  resetViewCache();
  _DETAIL_LOADED=false;
  _DETAIL_LOADING=null;

  resetPages();
  clearAllPagers();
  el('l1').innerHTML='<div class="empty">正在加载数据...</div>'; el('l2').innerHTML=''; el('l3').innerHTML=''; el('l4').innerHTML='';

  const baseUrl = './data/'+file;
  const cacheKey = _cacheKeyForUrl(baseUrl);
  const ts = String((q && q.data_ts) || '').trim();
  let usedCache = false;
  if(!force){
    const cached = await _cacheGet(cacheKey);
    const d0 = readCachedJsonValue(cached);
    if(d0){
      try{
        DATA=d0;
        buildIndex();
        render();
        usedCache = true;
      }catch(e){}
    }
  }
  const url = baseUrl + ((force || ts) ? ('?_=' + encodeURIComponent(ts || Date.now())) : '');
  try{
    const resp = await fetch(url, (force || ts) ? {cache:'no-store'} : {});
    const loaded = await readRemoteJson(resp);
    const d = loaded && loaded.data ? loaded.data : null;
    DATA=d;
    buildIndex();
    render();
    if(!force && loaded && loaded.cacheValue){
      try{ await _cacheSet(cacheKey, loaded.cacheValue); }catch(e){}
    }
  }catch(e){

    if(!usedCache){
      DATA=null;
      el('l1').innerHTML='<div class="empty">未找到数据文件：'+esc(file)+'</div>';
    }
  }
}

let _DETAIL_LOADED=false;
let _DETAIL_LOADING=null;
async function _ensureDetailLoaded(force){
  if(_DETAIL_LOADED) return true;
  if(_DETAIL_LOADING) return await _DETAIL_LOADING;
  const file0 = (CURRENT && CURRENT.data_file) ? String(CURRENT.data_file||'').trim() : '';
  const df = (DATA && DATA.detail_file) ? String(DATA.detail_file||'').trim() : '';
  const detailFile = df || (file0 && file0.toLowerCase().endsWith('.json') ? (file0.slice(0,-5) + '_detail.json') : (file0 ? (file0 + '_detail.json') : ''));
  if(!detailFile) return false;
  const baseUrl = './data/' + detailFile;
  const cacheKey = _cacheKeyForUrl(baseUrl);
  const ts = String((CURRENT && CURRENT.data_ts) || '').trim();
  let usedCache = false;
  if(!force){
    const cached = await _cacheGet(cacheKey);
    const d0 = readCachedJsonValue(cached);
    if(d0 && d0.monster_items && typeof d0.monster_items === 'object'){
      try{
        Object.keys(d0.monster_items).forEach(k=>{
          const mon = IDX.monByName[k];
          if(mon && !Array.isArray(mon.items)){
            mon.items = d0.monster_items[k];
          }
        });
        _DETAIL_LOADED = true;
        usedCache = true;
      }catch(e){}
    }
  }
  _DETAIL_LOADING = (async function(){
    try{
      const url = baseUrl + (ts ? ('?_=' + encodeURIComponent(ts)) : ('?_=' + Date.now()));
      const resp = await fetch(url, {cache:'no-store'});
      const loaded = await readRemoteJson(resp);
      const d = loaded && loaded.data ? loaded.data : null;
      if(d && d.monster_items && typeof d.monster_items === 'object'){
        Object.keys(d.monster_items).forEach(k=>{
          const mon = IDX.monByName[k];
          if(mon){
            mon.items = d.monster_items[k];
          }
        });
        _DETAIL_LOADED = true;
        if(loaded && loaded.cacheValue){
          try{ await _cacheSet(cacheKey, loaded.cacheValue); }catch(e){}
        }
        return true;
      }
    }catch(e){

      if(usedCache) return true;
    }finally{
      _DETAIL_LOADING = null;
    }
    return false;
  })();
  return await _DETAIL_LOADING;
}

function renderHome(){
  const wrap=el('cards');
  const qs = (SITE && Array.isArray(SITE.drop_queries)) ? SITE.drop_queries.filter(x=>x && x.id) : [];
  if(SITE && SITE.drop_enabled === false){ el('homeEmpty').style.display='block'; el('homeEmpty').textContent='当前站点暂未开启爆率查询，请先查看官网公告或联系玩家社群。'; wrap.innerHTML=''; return; }

  if(!qs.length){ el('homeEmpty').style.display='block'; el('homeEmpty').textContent='未配置任何版本，请先在工具箱里添加爆率查询版本'; wrap.innerHTML=''; return; }
  el('homeEmpty').style.display='none';

  const versionDownloadByName = {};
  try{
    if(SITE && Array.isArray(SITE.versions)){
      SITE.versions.forEach(v=>{
        const nm = String(v && v.name || '').trim();
        let dl = String(v && v.download_url || '').trim();
        if(!nm || !dl || versionDownloadByName[nm]) return;
        try{
          if(/^\/\//.test(dl)) dl = 'http:' + dl;
          if(!/^https?:\/\//i.test(dl) && !/^[./#]/.test(dl) && !/^[a-zA-Z]:[\\/]/.test(dl)){
            if(/^localhost(?::\d+)?(\/.*)?$/i.test(dl) || /^[\w.-]+\.[a-zA-Z]{2,}(?::\d+)?(\/.*)?$/.test(dl)){
              dl = 'http://' + dl;
            }
          }
        }catch(e0){}
        versionDownloadByName[nm] = dl;
      });
    }
  }catch(e1){}

  const selectById = function(id){

    id = String(id || '').trim();
    if(!id) return;
    const qsList = (SITE && Array.isArray(SITE.drop_queries)) ? SITE.drop_queries.filter(x=>x && x.id) : [];
    const q = qsList.find(x=>String(x.id||'')===id) || null;
    if(!q) return;
    try{ el('verSel').value = id; }catch(e){}
    try{
      if(history && history.replaceState){
        history.replaceState(null, '', './droprate.html?v=' + encodeURIComponent(id));
      }
    }catch(e2){}
    setVersion(q);
    STATE.tab='item';
    setTabActive('item');
    setView('main');
    loadDataFor(q);
  };

  if(STATE.mode === 'lite'){
    try{ el('homeLite').style.display='block'; }catch(e){}
    try{ wrap.style.display='none'; }catch(e2){}
    const kw = String(STATE.homeKw || '').trim().toLowerCase();
    let out = qs.slice();
    if(kw){
      out = out.filter(q=>{
        const nm = String(q && q.name || '').trim().toLowerCase();
        const tp = String(q && q.type || '').trim().toLowerCase();
        const intro = String(q && q.intro || '').trim().toLowerCase();
        return nm.indexOf(kw) >= 0 || tp.indexOf(kw) >= 0 || intro.indexOf(kw) >= 0;
      });
    }
    if(STATE.sort === 'name'){
      out = out.slice().sort((a,b)=>String(a && a.name || '').localeCompare(String(b && b.name || ''), 'zh'));
    }
    let html = '';
    out.forEach(q=>{
      const vid = String(q && q.id || '');
      const nm = String(q && q.name || '').trim() || vid;
      html += '<button class="tagBtn" type="button" data-id="'+esc(vid)+'">'+esc(nm)+'</button>';
    });
    el('homeTags').innerHTML = html || '<div class="empty">暂无匹配版本</div>';
    try{
      el('homeTags').querySelectorAll('[data-id]').forEach(btn=>{
        btn.onclick = function(){ selectById(this.getAttribute('data-id')); };
      });
    }catch(e3){}
    return;
  }

  try{ el('homeLite').style.display='none'; }catch(e4){}
  try{ wrap.style.display='grid'; }catch(e5){}
  let out = qs.slice();
  if(STATE.sort === 'name'){
    out = out.slice().sort((a,b)=>String(a && a.name || '').localeCompare(String(b && b.name || ''), 'zh'));
  }
  let html='';
  out.forEach(q=>{
    const img = String(q.image||'').trim();
    const intro = String(q.intro||'').trim();
    const vid = String(q.id||'');
    const go = '?v='+encodeURIComponent(vid);
    const downloadUrl = String(versionDownloadByName[String(q.name||'').trim()] || '').trim();
    html += '<div class="card">';
    if(img){ html += '<div class="cardImg"><img src="'+esc(img)+'" alt=""/></div>'; }
    else{ html += '<div class="cardImg">'+esc(String(q.type||'版本'))+'</div>'; }
    html += '<div class="cardB">';
    html += '<div class="cardT">'+esc(String(q.name||'未命名'))+'</div>';
    html += '<div class="cardD">'+esc(intro || ' ')+'</div>';
    html += '<div class="cardA">';
    if(downloadUrl){ html += '<a class="btn ghost" href="'+esc(downloadUrl)+'" target="_blank" rel="noopener">版本下载</a>'; }
    html += '<a class="btn primary" href="'+esc(go)+'">进入查询</a>';
    html += '</div></div></div>';
  });

  wrap.innerHTML=html;

  try{
    wrap.querySelectorAll('[data-act="select"]').forEach(btn=>{
      btn.onclick = function(){ selectById(this.getAttribute('data-id')); };
    });
  }catch(e6){}
}

function initNav(){
  document.querySelectorAll('.navBtn').forEach(b=>{
    b.onclick=function(){
      const tab=this.getAttribute('data-tab');
      if(tab==='home'){
        STATE.tab='home';
        resetPages();
        setTabActive('home');
        setView('home');

        try{
          if(history && history.replaceState){
            history.replaceState(null, '', './droprate.html');
          }
        }catch(e){}
        renderHome();
        return;
      }
      if(!CURRENT){
        STATE.tab='home';
        resetPages();
        setTabActive('home');
        setView('home');

        renderHome();
        return;
      }
      STATE.tab=tab;
      resetPages();
      setTabActive(tab);
      setView('main');

      if((tab==='monster' || tab==='map') && !_DETAIL_LOADED){
        clearAllPagers();
        el('l2').innerHTML='<div class="empty">正在加载怪物掉落明细...</div>';
        el('l3').innerHTML=''; el('l4').innerHTML='';

        _ensureDetailLoaded(false).then(()=>{ try{ render(); }catch(e){} });
        return;
      }
      render();
    };
  });
}

function initTool(){
  function _applyModeButtons(){
    try{
      el('modeStd').classList.toggle('active', STATE.mode === 'std');
      el('modeLite').classList.toggle('active', STATE.mode === 'lite');
    }catch(e){}
    try{ el('verSel').style.display = ''; }catch(e2){}
  }

  function _refreshVersionLabels(){
    try{
      const qs = (SITE && Array.isArray(SITE.drop_queries)) ? SITE.drop_queries.filter(x=>x && x.id) : [];
      const byId = {};
      qs.forEach(q=>{ byId[String(q && q.id || '')] = q; });
      const cur = String(el('verSel').value || '').trim();
      el('verSel').querySelectorAll('option').forEach(o=>{
        const id = String(o.value || '').trim();
        if(!id) return;
        const q = byId[id] || null;
        if(!q) return;
        if(STATE.mode === 'lite'){
          o.textContent = String(q.name||'').trim() || id;
        }else{
          o.textContent = String(q.name||'') + (q.type ? (' - '+String(q.type||'')) : '');
        }
      });
      try{ el('verSel').value = cur; }catch(e2){}
    }catch(e){}
  }

  try{
    el('modeStd').onclick=function(ev){
      try{ if(ev){ ev.preventDefault(); ev.stopPropagation(); } }catch(e){}
      STATE.mode='std';
      _applyModeButtons();
      _refreshVersionLabels();
      STATE.tab = 'home';
      try{ el('verSel').value = ''; }catch(e2){}
      resetPages();
      setTabActive('home');
      setView('home');
      try{
        if(history && history.replaceState){
          history.replaceState(null, '', './droprate.html');
        }
      }catch(e3){}
      renderHome();
    };

    el('modeLite').onclick=function(ev){
      try{ if(ev){ ev.preventDefault(); ev.stopPropagation(); } }catch(e){}
      STATE.mode='lite';
      _applyModeButtons();
      _refreshVersionLabels();
      STATE.tab = 'home';
      try{ el('verSel').value = ''; }catch(e2){}
      resetPages();
      setTabActive('home');
      setView('home');
      try{
        if(history && history.replaceState){
          history.replaceState(null, '', './droprate.html');
        }
      }catch(e3){}
      renderHome();
    };

  }catch(e){}
  _applyModeButtons();

  function _bindKw(id, key){
    try{
      const node = el(id);
      if(!node) return;
      const listId = 'l' + String(id || '').replace('ckw', '');
      node.oninput=function(){ STATE[key]=this.value||''; PAGE_STATE[listId]=1; if(STATE.tab!=='home') scheduleRender(); };
    }catch(e){}
  }

  _bindKw('ckw1','kw1');
  _bindKw('ckw2','kw2');
  _bindKw('ckw3','kw3');
  _bindKw('ckw4','kw4');

  el('showAll').onchange=function(){ STATE.showAll=!!this.checked; resetPages(); render(); };
  try{
    el('sortSel').onchange=function(){ STATE.sort=String(this.value||'default'); resetPages(); if(STATE.tab==='home') renderHome(); else render(); };

  }catch(e){}
  try{
    el('homeKw').oninput=function(){ STATE.homeKw = this.value || ''; if(STATE.tab==='home') renderHome(); };
  }catch(e3){}
  try{
    el('helpBtn').onclick=function(){
      alert('使用说明\n\n1) 先选择查询版本进入查询\n2) 精简模式：版本选择以名称按钮形式显示\n3) 排序可按名称/爆率排序（物品列表支持爆率排序）\n4) 四列顶部输入框可过滤列表');
    };
  }catch(e){}
}

function initVersionSelector(){
  const sel=el('verSel');
  sel.innerHTML='';
  const qs = (SITE && Array.isArray(SITE.drop_queries)) ? SITE.drop_queries.filter(x=>x && x.id) : [];
  const opt0=document.createElement('option');
  opt0.value='';
  opt0.textContent='选择查询版本';
  sel.appendChild(opt0);
  qs.forEach(q=>{
    const o=document.createElement('option');
    o.value=String(q.id||'');
    o.textContent = (STATE.mode === 'lite') ? (String(q.name||'').trim() || String(q.id||'')) : (String(q.name||'') + (q.type ? (' - '+String(q.type||'')) : ''));
    sel.appendChild(o);
  });
  sel.onchange=function(){
    const id=String(sel.value||'').trim();
    if(!id){
      CURRENT = null;
      STATE.tab='home';
      resetPages();
      setTabActive('home');
      setView('home');

      try{
        if(history && history.replaceState){
          history.replaceState(null, '', './droprate.html');
        }
      }catch(e){}
      renderHome();
      return;
    }
    const q = qs.find(x=>String(x && x.id || '') === id) || null;
    if(!q) return;
    try{
      if(history && history.replaceState){
        history.replaceState(null, '', './droprate.html?v=' + encodeURIComponent(id));
      }
    }catch(e2){}
    setVersion(q);
    STATE.tab='item';
    setTabActive('item');
    setView('main');
    loadDataFor(q);
  };
}

/* 将站点标题、页脚与头部品牌同步为当前站点信息。 */
function applySiteIdentity(site){
  const tt = String((site && (site.title || site.name)) || '').trim();
  if(!tt) return;
  document.title = tt + ' - 爆率查询';
  el('siteTitle').textContent = tt + ' · 爆率情报';
  el('footTxt').textContent = '玛法情报中心 - ' + tt;
  try{ el('hdrName').textContent = tt; }catch(e){}
}

/* 根据后台开关同步爆率查询页状态，避免显示可见但不可用的入口。 */
function syncDropUiState(){
  const disabled = !!(SITE && SITE.drop_enabled === false);
  ['item','monster','map','npc'].forEach(tab=>{
    try{
      const btn = document.querySelector('.navBtn[data-tab="' + tab + '"]');
      if(btn) btn.classList.toggle('disabled', disabled);
    }catch(e){}
  });
  try{ el('verSel').disabled = disabled; }catch(e){}
  try{
    if(disabled){
      el('verInfo').textContent = '爆率查询暂未开放';
      el('guideBtn').classList.add('disabled');
      el('guideBtn').href = '#';
    }
  }catch(e){}
}

/* 优先使用构建阶段内联的站点数据，失败时再回退到远程读取，提高首屏速度与稳定性。 */
async function bootstrapSite(){
  let s = null;
  try{
    if(window.__SITE_INLINE__ && typeof window.__SITE_INLINE__ === 'object') s = window.__SITE_INLINE__;
  }catch(e){}
  try{
    const resp = await fetch('./data/site.json?_=' + Date.now(), {cache:'no-store'});
    s = await resp.json();
  }catch(e){
    if(!s || typeof s !== 'object' || !Object.keys(s).length){
      throw e;
    }
  }
  SITE = s || {};
  applySiteIdentity(SITE);
  initNav();
  initTool();
  if(SITE && SITE.drop_reverse){
    STATE.sort = 'rate';
    try{ el('sortSel').value = 'rate'; }catch(e){}
  }
  syncDropUiState();
  initVersionSelector();

  if(SITE && SITE.drop_enabled === false){
    STATE.tab='home';
    setTabActive('home');
    setView('home');
    renderHome();
    return;
  }

  const params=qsp();
  const qsList = (SITE && Array.isArray(SITE.drop_queries)) ? SITE.drop_queries.filter(x=>x && x.id) : [];
  const vid = String(params.v||'').trim();
  if(!vid){
    STATE.tab='home';
    setTabActive('home');
    setView('home');
    renderHome();
    return;
  }
  const q = qsList.find(x=>String(x.id||'')===vid) || qsList[0] || null;
  if(q){
    el('verSel').value = String(q.id||'');
    setVersion(q);
    STATE.tab='item';
    setTabActive('item');
    setView('main');
    loadDataFor(q);
  }else{
    STATE.tab='home';
    setTabActive('home');
    setView('home');
    renderHome();
  }
}

bootstrapSite().catch(()=>{
  el('viewHome').style.display='block';
  el('cards').innerHTML='<div class="empty">未找到 site.json</div>';
});

</script>
</body></html>"""
