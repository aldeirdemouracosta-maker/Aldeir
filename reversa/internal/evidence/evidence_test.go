package evidence

import "testing"

func TestAddCarimbaConfiancaDigestEAlvo(t *testing.T) {
	l := &Log{Subject: "abc"}
	a := l.Add("t", "", "saida", "")
	b := l.AddAs(Inferred, "llm", "", "saida", "hipótese")
	if a.Confidence != Observed || b.Confidence != Inferred {
		t.Fatalf("confiança: %s %s", a.Confidence, b.Confidence)
	}
	if a.Digest != b.Digest || len(a.Digest) != 64 {
		t.Fatalf("digest: %q %q", a.Digest, b.Digest)
	}
	if a.Subject != "abc" || a.ID != 1 || b.ID != 2 {
		t.Fatalf("registro: %+v %+v", a, b)
	}
}
