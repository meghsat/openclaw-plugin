const LEMONADE_BASE_URL = "http://localhost:8000/api/v1";
const LEMONADE_IMAGE_MODEL = "SD-1.5";

export default {
  id: "lemonade-image",
  name: "Lemonade Image Generation",
  description: "Local image generation via Lemonade stable-diffusion.cpp backend",
  configSchema: { type: "object", additionalProperties: false, properties: {} },
  register(api) {
    api.registerImageGenerationProvider({
      id: "lemonade",
      label: "Lemonade",
      defaultModel: LEMONADE_IMAGE_MODEL,
      models: [LEMONADE_IMAGE_MODEL],
      capabilities: {
        generate: {
          maxCount: 1,
          supportsSize: false,
          supportsAspectRatio: false,
          supportsResolution: false,
        },
        edit: {
          enabled: false,
          maxCount: 0,
          maxInputImages: 0,
        },
      },
      async generateImage(req) {
        const response = await fetch(`${LEMONADE_BASE_URL}/images/generations`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: "Bearer lemonade",
          },
          body: JSON.stringify({
            model: req.model || LEMONADE_IMAGE_MODEL,
            prompt: req.prompt,
            n: req.count ?? 1,
          }),
        });

        if (!response.ok) {
          const text = await response.text().catch(() => "");
          throw new Error(
            `Lemonade image generation failed (${response.status}): ${text || response.statusText}`,
          );
        }

        const data = await response.json();
        const images = (data.data ?? [])
          .map((entry, index) => {
            if (!entry.b64_json) return null;
            return {
              buffer: Buffer.from(entry.b64_json, "base64"),
              mimeType: "image/png",
              fileName: `image-${index + 1}.png`,
            };
          })
          .filter((entry) => entry !== null);

        if (images.length === 0) {
          throw new Error("Lemonade returned no images");
        }

        return { images, model: req.model || LEMONADE_IMAGE_MODEL };
      },
    });
  },
};
