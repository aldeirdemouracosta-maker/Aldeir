namespace ReaStudio.Core.Binary;

public enum BinaryFormat { Unknown, Pe, Elf }

public sealed record BinaryInfo(BinaryFormat Format, int? Bits, string? Architecture);

/// <summary>Detecta PE/ELF pelo cabeçalho. Consoles (PS1, Saturn, SNES, Mega Drive...) ficam para fases futuras.</summary>
public static class BinaryFormatDetector
{
    public static BinaryInfo Detect(ReadOnlySpan<byte> h)
    {
        if (h.Length >= 0x40 && h[0] == 'M' && h[1] == 'Z')
        {
            int pe = BitConverter.ToInt32(h.Slice(0x3C, 4));
            if (pe > 0 && pe + 26 <= h.Length && h[pe] == 'P' && h[pe + 1] == 'E' && h[pe + 2] == 0 && h[pe + 3] == 0)
            {
                ushort machine = BitConverter.ToUInt16(h.Slice(pe + 4, 2));
                ushort magic = BitConverter.ToUInt16(h.Slice(pe + 24, 2));
                int? bits = magic == 0x20B ? 64 : magic == 0x10B ? 32 : null;
                string? arch = machine switch { 0x14C => "x86", 0x8664 => "x86-64", 0xAA64 => "ARM64", 0x1C0 or 0x1C4 => "ARM", _ => null };
                return new BinaryInfo(BinaryFormat.Pe, bits, arch);
            }
            return new BinaryInfo(BinaryFormat.Unknown, null, null);
        }
        if (h.Length >= 20 && h[0] == 0x7F && h[1] == 'E' && h[2] == 'L' && h[3] == 'F')
        {
            int? bits = h[4] == 1 ? 32 : h[4] == 2 ? 64 : null;
            bool le = h[5] != 2;
            ushort machine = le ? BitConverter.ToUInt16(h.Slice(18, 2)) : (ushort)((h[18] << 8) | h[19]);
            string? arch = machine switch { 3 => "x86", 62 => "x86-64", 40 => "ARM", 183 => "ARM64", 8 => "MIPS", 243 => "RISC-V", _ => null };
            return new BinaryInfo(BinaryFormat.Elf, bits, arch);
        }
        return new BinaryInfo(BinaryFormat.Unknown, null, null);
    }

    public static BinaryInfo DetectFile(string path)
    {
        var buf = new byte[4096];
        using var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        int n = fs.Read(buf, 0, buf.Length);
        return Detect(buf.AsSpan(0, n));
    }
}
