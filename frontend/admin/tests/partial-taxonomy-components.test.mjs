import test from 'node:test';
import assert from 'node:assert/strict';

// Small native-DOM harness: execute the production components and their event
// handlers without adding a browser dependency to this framework-free app.
const registry = new Map();
class Element {
  constructor(tag = '') { this.tagName = tag; this.children = []; this.attributes = new Map(); this.dataset = {}; this.handlers = new Map(); this.value = ''; this.ownText = ''; }
  set textContent(value) { this.ownText = String(value); this.children = []; }
  get textContent() { return this.ownText + this.children.map(c => typeof c === 'string' ? c : c.textContent).join(' '); }
  append(...children) { this.children.push(...children); }
  prepend(...children) { this.children.unshift(...children); }
  replaceChildren(...children) { this.ownText = ''; this.children = children; }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  addEventListener(type, handler) { this.handlers.set(type, [...(this.handlers.get(type) ?? []), handler]); }
  removeEventListener() {}
  dispatch(type) { for (const handler of this.handlers.get(type) ?? []) handler({ preventDefault() {} }); }
  querySelector() { return null; }
  querySelectorAll() { return []; }
}
globalThis.requestAnimationFrame = () => 1;
globalThis.HTMLElement = Element;
globalThis.customElements = { define(name, constructor) { registry.set(name, constructor); } };
globalThis.document = { addEventListener() {}, removeEventListener() {}, visibilityState: 'visible', querySelector() { return null; },
  createElement(tag) { const Constructor = registry.get(tag); return Constructor ? new Constructor() : new Element(tag); } };
globalThis.window = { location: { search: '', pathname: '/' }, history: { replaceState() {} },
  setInterval() { return 1; }, clearInterval() {}, setTimeout() { return 1; }, clearTimeout() {} };
const { api, queryStore } = await import('../dist/assets/app-context.js');
const { TaxonomyReviewPage } = await import('../dist/assets/pages/taxonomy-review-page.js');
const { InputsPage } = await import('../dist/assets/pages/inputs-page.js');
const { GenerationPage } = await import('../dist/assets/pages/generation-page.js');
const { DashboardOverview } = await import('../dist/assets/pages/dashboard-overview.js');
const { reviewRunId } = await import('../dist/assets/pages/taxonomy-review-state.js');
function nodes(root) { return [root, ...root.children.filter(c => typeof c !== 'string').flatMap(nodes)]; }
function find(root, tag, label) { return nodes(root).find(n => n.tagName === tag && (label === undefined || n.textContent === label)); }
function click(root, label) { const node = find(root, 'button', label); assert.ok(node, label); node.dispatch('click'); }
async function tick() { await new Promise(resolve => setImmediate(resolve)); }
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }
const topic = { id: 11, topic_id: 4, name: '<b>Access fees</b>', description: 'Fees impede access.', support_count: 4, continuity_decision: 'new', antecedents: [
  { id: 1, name: 'Fees', description: 'Cost', question_id: 2, support_count: 2, relationship: 'equivalent', reconciliation_decision_id: 9 },
  { id: 2, name: 'Charges', description: 'Costs', question_id: 3, support_count: 2, relationship: 'equivalent', reconciliation_decision_id: 9 },
] };
const run = { id: 6, status: 'ready_for_review', evidence_count: 6, evidence_with_topic_count: 4, evidence_without_topic_count: 2, topic_count: 1, theme_count: 0, noise_count: 2, gate_passed: true, publication_failures: [], topics: [topic], clusters: [{ id: 3, question_id: 2, support_count: 2, outcome: 'unresolved', reasons: ['name_blank'], provisional_name: null }], truncated: false };

test('review page automatically loads coverage, merge provenance, bounded rejection and explicitly loaded evidence', async () => {
  const calls = [];
  api.taxonomyRuns = async options => { calls.push(options); return [{id:6,status:'ready_for_review'}]; };
  api.taxonomyRun = async (id, options) => { calls.push(options); return run; };
  api.taxonomyTopicEvidence = async (id, revision, offset, options) => { calls.push(options); return {offset,page_size:50,items:[{id:1,original_input_id:8,segment_input_id:null,text:'Private answer'}]}; };
  const page = new TaxonomyReviewPage(); page.connectedCallback();
  assert.equal(find(page,'input'),undefined);
  assert.equal(find(page,'form'),undefined);
  await tick();
  assert.match(page.textContent,/Partial topic coverage · 6 total evidence · 4 with topics · 2 without topics/);
  assert.match(page.textContent,/0 optional themes/);
  assert.match(page.textContent,/Fees · provisional 1 · question 2 · 2 evidence · equivalent/);
  assert.match(page.textContent,/Charges · provisional 2/);
  assert.match(page.textContent,/unresolved · Reasons: name_blank/);
  assert.match(page.textContent,/does not make the answers invalid/);
  assert.ok(find(page,'h4','<b>Access fees</b>')); // model label is text, not parsed HTML
  assert.equal(nodes(page).filter(n => n.tagName === 'b').length,0);
  assert.ok(!page.textContent.includes('Private answer'));
  click(page,'View canonical evidence'); await tick();
  assert.match(page.textContent,/original 8: Private answer/);
  assert.ok(calls.every(c => c.operatorToken === undefined));
  page.disconnectedCallback();
});

test('stale review, evidence, refresh and navigation responses cannot replace current state', async () => {
  api.taxonomyRuns = async () => [{id:6,status:'running'},{id:7,status:'running'}];
  const first = deferred();
  api.taxonomyRun = async id => id === 6 ? first.promise : {...run,id:7,topics:[]};
  const page = new TaxonomyReviewPage(); page.connectedCallback(); await tick();
  assert.ok(nodes(page).some(n => n.getAttribute('label') === 'Loading review…'));
  const selector = find(page,'select'); selector.value = '7'; selector.dispatch('change'); await tick();
  assert.match(page.textContent,/Run 7/);
  first.resolve(run); await tick();
  assert.ok(find(page,'h2','Run 7 · ready_for_review'));
  assert.match(page.textContent,/No canonical topics yet/);
  api.taxonomyRun = async () => run;
  click(page,'Refresh'); await tick();
  const evidence = deferred(); api.taxonomyTopicEvidence = async () => evidence.promise;
  click(page,'View canonical evidence');
  page.disconnectedCallback();
  evidence.resolve({offset:0,page_size:50,items:[{id:1,original_input_id:2,text:'Must not return'}]}); await tick();
  assert.ok(!page.textContent.includes('Must not return'));
  page.disconnectedCallback();
});

test('review handles server errors, retry and empty runs', async () => {
  api.taxonomyRuns = async () => { throw new Error('Server unavailable'); };
  const page = new TaxonomyReviewPage(); page.connectedCallback(); await tick();
  assert.ok(find(page,'ui-alert'));
  assert.ok(!page.textContent.includes('canonical topics'));
  api.taxonomyRuns = async () => [];
  click(page,'Try again'); await tick(); assert.match(page.textContent,/No taxonomy runs yet/);
  page.disconnectedCallback();
  assert.equal(reviewRunId(new URLSearchParams('run=-1')),null);
  assert.equal(reviewRunId(new URLSearchParams('run=9007199254740992')),null);
  assert.equal(reviewRunId(new URLSearchParams('run=6')),6);
});

test('input view renders published arrays and normal empty associations without a taxonomy state', async () => {
  const input = { id:1,question_context:{question_text:'What matters?'},original_text:'Answer',status:'completed',published_taxonomy_run_id:6,topics:[],themes:[] };
  api.inputs = async () => [input,{...input,id:2,topics:[{id:4,name:'Access'}]}];
  const page = new InputsPage(); page.connectedCallback(); await tick();
  assert.match(page.textContent,/Topics: None/); assert.match(page.textContent,/Themes: None/);
  assert.match(page.textContent,/Topics: Access/); assert.match(page.textContent,/Published run 6/);
  assert.ok(!page.textContent.includes('taxonomy_state'));
  const old = deferred(); api.inputs = async () => old.promise; click(page,'Refresh');
  api.inputs = async () => []; click(page,'Refresh'); await tick();
  old.resolve([{...input,original_text:'Stale answer'}]); await tick();
  assert.match(page.textContent,/No inputs on this page/); assert.ok(!page.textContent.includes('Stale answer'));
  page.disconnectedCallback();
});

test('overview renders partial totals and topic recommendations without themes; theme empty is normal', async () => {
  queryStore.invalidate('');
  api.summary = async () => ({evidence_count:6,evidence_with_topic_count:4,evidence_without_topic_count:2,topic_coverage:'partial',theme_count:0,topic_count:1,article_count:0,awaiting_approval_count:0,failed_generation_count:0});
  const item = {type:'topic',key:4,name:'Access',description:'Costs',evidence_count:4,article_count:0,approved_article_count:0,coverage_state:'uncovered',generation_eligible:true,explanation:'Evidence supports an article'};
  const types = [];
  api.taxonomy = async query => { types.push(query.type); return {items:query.type==='topic'?[item]:[],total:query.type==='topic'?1:0,page:1,page_size:25}; };
  api.recommendations = async type => { types.push(type); return {items:type==='topic'?[item]:[]}; };
  window.location.search = '';
  const page = new DashboardOverview(); page.connectedCallback(); await tick();
  assert.match(page.textContent,/Evidence 6 Partial topic coverage/);
  assert.match(page.textContent,/With topics 4/); assert.match(page.textContent,/Without topics 2/);
  assert.ok(types.every(type => type === 'topic'));
  assert.ok(nodes(page).some(n => n.tagName==='a' && n.href.includes('type=topic') && n.href.includes('key=4')));
  click(page,'Themes'); await tick();
  assert.match(page.textContent,/Themes are optional. Browse Topics/);
  page.disconnectedCallback();
});

test('topic generation screen carries canonical evidence through template and job creation with no themes', async () => {
  window.location.search = '?strategy=specific&type=topic&key=4';
  const calls = [];
  api.taxonomyDetail = async (type,key) => { calls.push([type,key]); return {type:'topic',key:4,name:'Access',generation_eligible:true}; };
  api.evidence = async (type,key) => { calls.push([type,key]); return {total:1,items:[{id:'original:8',type:'original',original_input_id:8,original_text:'Canonical answer',excerpt:'Canonical answer',question_context:null}]}; };
  api.articleTemplates = async () => [{id:1,name:'Article',status:'active',versions:[{id:12,version:1}]}];
  api.previewArticleTemplate = async () => ({rendered_html:'<article>Preview</article>'});
  let payload;
  api.createGenerationJob = async body => { payload = body; return {id:42,status:'pending',attempts:0,taxonomy_name:'Access'}; };
  const page = new GenerationPage(); page.connectedCallback(); await tick();
  assert.match(page.textContent,/Canonical answer/);
  assert.match(page.textContent,/1 selected/);
  assert.deepEqual(calls,[['topic','4'],['topic',4]]);
  click(page,'Choose a template'); await tick();
  assert.equal(find(page,'button','Add guidance').disabled,false);
  click(page,'Add guidance');
  find(page,'form').dispatch('submit');
  click(page,'Generate article'); await tick();
  assert.deepEqual(payload,{strategy:'specific',taxonomy_type:'topic',taxonomy_key:'4',template_version_id:12,editorial_guidance:null,evidence_ids:['original:8']});
  assert.match(page.textContent,/Generation progress/);
  page.disconnectedCallback();
  window.location.search = '';
});

test('generation screen ignores a late target response after navigation away', async () => {
  window.location.search = '?type=topic&key=4';
  const target = deferred(); api.taxonomyDetail = async () => target.promise;
  let evidenceCalls = 0; api.evidence = async () => { evidenceCalls += 1; return {items:[],total:0}; };
  const page = new GenerationPage(); page.connectedCallback();
  page.disconnectedCallback();
  target.resolve({type:'topic',key:4,name:'Stale',generation_eligible:true}); await tick();
  assert.equal(evidenceCalls,0);
  assert.ok(!page.textContent.includes('Stale'));
  window.location.search = '';
});

test('inputs applies URL filters across pages, clears filters and rejects stale results', async () => {
  const calls = [];
  const item = {id:1,source:'test',created_at:'2026-01-01',submission_key:'row1',question_context:{question_text:'What matters?',form_key:'form',question_key:'Q1',question_version:1},original_text:'Answer',status:'completed',published_taxonomy_run_id:6,topics:[],themes:[]};
  api.inputs = async (offset, options, filters) => {calls.push({offset,options,filters}); return Array(50).fill(item);};
  window.location.search = '?status=new&has_topic=false&offset=50';
  let url;
  const originalReplace = window.history.replaceState;
  window.history.replaceState = (state,title,value) => {url=value;};
  const page = new InputsPage(); page.connectedCallback(); await tick();
  assert.deepEqual(calls[0].filters,{status:'new',has_topic:false});
  assert.equal(calls[0].offset,50);
  click(page,'Next'); await tick();
  assert.equal(calls.at(-1).offset,100); assert.match(url,/has_topic=false/);
  const control = name => nodes(page).find(n => n.name===name);
  control('search').value='fees';
  find(page,'form').dispatch('submit'); await tick();
  assert.equal(calls.at(-1).offset,0); assert.equal(calls.at(-1).filters.search,'fees');
  assert.match(url,/search=fees/); assert.ok(!url.includes('offset='));
  const old=deferred(); api.inputs=async()=>old.promise;
  click(page,'Refresh');
  api.inputs=async(offset,options,filters)=>{calls.push({offset,options,filters});return [];};
  click(page,'Clear filters'); await tick();
  assert.deepEqual(calls.at(-1).filters,{}); assert.equal(url,'/inputs');
  assert.equal(control('search').value,'');
  old.resolve([{...item,original_text:'Stale filtered response'}]); await tick();
  assert.ok(!page.textContent.includes('Stale filtered response'));
  control('source').value='test';
  const before=calls.length;find(page,'form').dispatch('submit');await tick();
  assert.equal(calls.length,before);assert.match(page.textContent,/Enter both Source and Form key/);
  page.disconnectedCallback();
  window.location.search='';window.history.replaceState=originalReplace;
});
