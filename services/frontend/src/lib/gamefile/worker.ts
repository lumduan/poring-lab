// The finder's Web Worker: no DOM, no page state, no network. It receives one File, reads it by
// slices and posts back a ScanResult. The page terminates it on a timeout (run.ts).

import { failed, fileReader, scanSource } from "./scan.ts";

self.onmessage = async (event: MessageEvent<unknown>) => {
  const file = event.data;
  if (!(file instanceof Blob) || !("name" in file)) {
    postMessage(failed("", "No file was given to the finder."));
    return;
  }
  const f = file as File;
  postMessage(await scanSource(fileReader(f), f.name, f.size));
};
