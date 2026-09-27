// png2bc7 <in.png> <out.dds>: encodes a PNG as a single-mip BC7 DDS (the format IC's UI textures use).
using BCnEncoder.Encoder;
using BCnEncoder.ImageSharp;
using BCnEncoder.Shared;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;

var encoder = new BcEncoder();
encoder.OutputOptions.Format = CompressionFormat.Bc7;
encoder.OutputOptions.GenerateMipMaps = false;
encoder.OutputOptions.Quality = CompressionQuality.BestQuality;
encoder.OutputOptions.FileFormat = OutputFileFormat.Dds;
using var image = Image.Load<Rgba32>(args[0]);
using var output = File.Create(args[1]);
encoder.EncodeToStream(image, output);
