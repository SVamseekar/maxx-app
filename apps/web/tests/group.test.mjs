import assert from "node:assert/strict";
import test from "node:test";
import { activeBuyers, buyersAtOrAbove, chartDomain, demandSteps, median, percentBelow } from "../app/blocs/group.ts";

const member = (id, max_price, status = "HELD") => ({ id, max_price, status });

test("people who left are not part of the group, but released commitments still were", () => {
  const buyers = activeBuyers([member("a", "150.00"), member("b", "140.00", "LEFT"), member("c", "130.00", "RELEASED"), member("d", "120.00", "WIN"), member("e", "oops")]);
  assert.deepEqual(buyers.map(b => b.id), ["a", "c", "d"]);
});

test("buyers at or above counts a limit equal to the price", () => {
  const limits = [100, 120, 120, 150];
  assert.equal(buyersAtOrAbove(limits, 120), 3);
  assert.equal(buyersAtOrAbove(limits, 120.01), 1);
  assert.equal(buyersAtOrAbove(limits, 99), 4);
  assert.equal(buyersAtOrAbove(limits, 151), 0);
  assert.equal(buyersAtOrAbove([], 10), 0);
});

test("median and percent below describe the group without counting equals", () => {
  assert.equal(median([100, 120, 140]), 120);
  assert.equal(median([100, 120, 140, 160]), 130);
  assert.equal(median([]), null);
  assert.equal(percentBelow([100, 120, 120, 150], 120), 25);
  assert.equal(percentBelow([100, 120, 120, 150], 150), 75);
  assert.equal(percentBelow([], 5), 0);
});

test("demand steps start at the whole group, drop at each limit and end at zero", () => {
  const steps = demandSteps([100, 120, 120, 150], 90, 160);
  assert.deepEqual(steps, [[90, 4], [100, 4], [100, 3], [120, 3], [120, 1], [150, 1], [150, 0], [160, 0]]);
  const counts = steps.map(step => step[1]);
  assert.deepEqual(counts, [...counts].sort((a, b) => b - a));
});

test("chart domain pads a one-buyer group and includes marker prices", () => {
  const [low, high] = chartDomain([150]);
  assert.ok(low < 150 && high > 150);
  const [lo2, hi2] = chartDomain([100, 150], [90, 180]);
  assert.ok(lo2 < 90 && hi2 > 180);
  assert.deepEqual(chartDomain([]), [0, 1]);
});
