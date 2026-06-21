import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const { downloadReport } = vi.hoisted(() => ({ downloadReport: vi.fn() }));
vi.mock("@/lib/api", () => ({ downloadReport }));

import { DownloadBar } from "@/components/report/DownloadBar";

beforeEach(() => downloadReport.mockReset());

// Downloads now go through the authenticated downloadReport() (fetch + blob) instead of bare
// <a download> links, so the Authorization header is sent and they don't 401 once a token is set.
test("downloads md and pdf via the authenticated helper (not bare links)", async () => {
  downloadReport.mockResolvedValue(undefined);
  render(<DownloadBar runId="r1" />);
  fireEvent.click(screen.getByText("Download .md"));
  await waitFor(() => expect(downloadReport).toHaveBeenCalledWith("r1", "md"));
  fireEvent.click(screen.getByText("Download .pdf"));
  await waitFor(() => expect(downloadReport).toHaveBeenCalledWith("r1", "pdf"));
});
