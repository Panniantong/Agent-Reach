// Run with Node + jsdom (see docs/nga.md). Uses the shipped extractor unchanged.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const script = fs.readFileSync(path.join(__dirname, '../agent_reach/channels/_nga_extract.js'), 'utf8');
const dom = new JSDOM(`<!doctype html><title>主题 NGA玩家社区</title>
  <div id="m_pbtntop"><a href="/read.php?tid=123&page=31">末页</a>
  <a href="/read.php?tid=999&page=999">其他主题</a></div>
  <span id="posterinfo0"><a href="/read.php?tid=123&page=10#pid456Anchor">#180</a>
  <a id="postauthor0" href="nuke.php?func=ucp&uid=42"><b name="nameinit">张</b>张三</a></span>
  <table><tr><td id="postcontainer0"><a id="pid456Anchor"></a>
  <span id="postdate0">2026-09-23 12:00</span><h3 id="postsubject0"></h3>
  <p id="postcontent0">正文<a href="/read.php?tid=122">引用</a>
  <img src="https://img.nga.cn/one.jpg"><img src="about:blank" data-srclazy="https://img.nga.cn/lazy.jpg">
  <img src="https://img.nga.cn/thumb.jpg" data-srcorg="https://img.nga.cn/original.jpg">
  <img class="smile_a2" src="https://img.nga.cn/smile.png">
  <img style="display:none" src="https://img.nga.cn/tracking.png"></p>
  <span id="alertc0">已编辑</span></td></tr></table>`,
  { url: 'https://bbs.nga.cn/read.php?tid=123&page=10', runScripts: 'outside-only' });
const data = dom.window.eval(script);
assert.equal(data.page, 10);
assert.equal(data.total_pages, 31);
assert.equal(data.title, '主题');
assert.equal(data.posts.length, 1);
assert.equal(data.posts[0].pid, '456');
assert.equal(data.posts[0].floor, 180);
assert.equal(data.posts[0].author, '张三');
assert.equal(data.posts[0].author_uid, '42');
assert.deepEqual(Array.from(data.posts[0].images, i => i.url), [
  'https://img.nga.cn/one.jpg', 'https://img.nga.cn/lazy.jpg', 'https://img.nga.cn/original.jpg']);
assert.equal(data.posts[0].links[0].url, 'https://bbs.nga.cn/read.php?tid=122');
dom.window.document.getElementById('postcontent0').remove();
assert.equal(dom.window.eval(script).posts[0].content_present, false);
console.log('NGA DOM extraction: passed');
