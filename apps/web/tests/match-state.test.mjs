import test from 'node:test';
import assert from 'node:assert/strict';
import { canCreateMatch } from '../app/blocs/matching.ts';
const result={requires_confirmation:false,candidates:[{product_key:'exact',confidence:.99},{product_key:'alternative',confidence:.79}]};
test('selecting an uncertain alternative still requires confirmation',()=>{
  assert.equal(canCreateMatch(result,'exact',false),true);
  assert.equal(canCreateMatch(result,'alternative',false),false);
  assert.equal(canCreateMatch(result,'alternative',true),true);
});
test('unrecognised custom product requires explicit confirmation',()=>{
  assert.equal(canCreateMatch(null,'',false),false);
  assert.equal(canCreateMatch(null,'',true),true);
});
test('ambiguous result needs confirmation even when a candidate score is high',()=>{
  assert.equal(canCreateMatch({...result,requires_confirmation:true},'exact',false),false);
});
