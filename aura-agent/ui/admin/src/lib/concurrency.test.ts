import { limiter } from "./concurrency";

test("no more than the limit run at once, and every task runs", async () => {
  const run = limiter(2);
  let running = 0;
  let peak = 0;
  const task = async (value: number) => {
    running += 1;
    peak = Math.max(peak, running);
    await new Promise((resolve) => setTimeout(resolve, 5));
    running -= 1;
    return value;
  };
  expect(await Promise.all([1, 2, 3, 4, 5].map((value) => run(() => task(value))))).toEqual([1, 2, 3, 4, 5]);
  expect(peak).toBe(2);
});
