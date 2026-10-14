import { render, screen } from "@testing-library/react";

import { WorkingWave } from "./WorkingWave";

test("a bar with a share done reports it; one without reports no value", () => {
  render(<>
    <WorkingWave form="bar" value={1 / 3} label="Floor plans: 1 of 3 documents done" />
    <WorkingWave form="bar" label="Starting" />
  </>);
  expect(screen.getByRole("progressbar", { name: "Floor plans: 1 of 3 documents done" })).toHaveAttribute("aria-valuenow", "33");
  expect(screen.getByRole("progressbar", { name: "Starting" })).not.toHaveAttribute("aria-valuenow");
});
