import test from 'node:test';
import assert from 'node:assert/strict';
import { inputsState, inputsSearch, inputFilterError } from '../dist/assets/pages/inputs-state.js';

test('input filters round trip with false presence, dates and identity attributes', () => {
  const state = inputsState(new URLSearchParams('search=%20fees%20&status=new&has_topic=false&topic=cost&theme=access&source=sheets&form_key=form&question_key=Q1&question_version=2&submission_key=row2&created_from=2026-01-01&created_to=2026-02-01&offset=50'));
  assert.equal(state.filters.search,'fees');
  assert.equal(state.filters.has_topic,false);
  assert.equal(state.filters.question_version,2);
  assert.equal(state.offset,50);
  assert.equal(inputFilterError(state.filters),null);
  assert.deepEqual(inputsState(new URLSearchParams(inputsSearch(state))),state);
});
test('invalid enum and paging state defaults safely; identity dependencies are visible', () => {
  for (const offset of ['-50','1','100050','Infinity','1e99']) {
    assert.equal(inputsState(new URLSearchParams({offset})).offset,0);
  }
  assert.deepEqual(inputsState(new URLSearchParams('status=bad&has_topic=bad&question_version=0&search=%20')), {filters:{},offset:0});
  assert.ok(inputFilterError({source:'sheets'}));
  assert.ok(inputFilterError({question_key:'Q1'}));
  assert.ok(inputFilterError({source:'sheets',form_key:'form',question_version:2}));
  assert.ok(inputFilterError({created_from:'2026-02-01',created_to:'2026-01-01'}));
  assert.equal(inputsSearch({filters:{},offset:0}),'');
});
