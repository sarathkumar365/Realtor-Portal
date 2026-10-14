import { render, screen } from "@testing-library/react";

import { Reading, Readings } from "./Readings";
import { StatusMark } from "./StatusMark";

test("a reading pairs its label with its value and unit", () => {
  render(
    <Readings>
      <Reading label="Changes" value={31} unit="branding items removed" marked />
      <Reading label="Status"><StatusMark kind="review">Needs review</StatusMark></Reading>
    </Readings>,
  );
  const terms = screen.getAllByRole("term").map((term) => term.textContent);
  expect(terms).toEqual(["Changes", "Status"]);
  const [changes, status] = screen.getAllByRole("definition");
  expect(changes).toHaveTextContent("31branding items removed");
  expect(status).toHaveTextContent("Needs review");
});
