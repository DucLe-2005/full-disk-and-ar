"use client";

import Image from "next/image";
import { useState } from "react";

import { artifactUrl } from "@/lib/artifacts";
import { ImageIcon } from "./icons";

type ArtifactImageProps = {
  path?: string | null;
  label: string;
  sizes?: string;
  eager?: boolean;
};

export function ArtifactImage({ path, label, sizes = "(max-width: 760px) 100vw, 50vw", eager = false }: ArtifactImageProps) {
  const url = artifactUrl(path);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);

  if (!path) return <div className="imagePlaceholder">No image artifact</div>;
  if (!url || failedUrl === url) {
    return <div className="imagePlaceholder"><ImageIcon /><span>{failedUrl === url ? `${label} unavailable` : label}</span><code>{path}</code></div>;
  }

  return <Image className="artifactImage solarImage" src={url} alt={label} width={1024} height={1024} sizes={sizes} loading={eager ? "eager" : "lazy"} decoding="async" unoptimized={/^https?:\/\//i.test(url)} onError={() => setFailedUrl(url)} />;
}
