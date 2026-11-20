import numpy as np

from nomsindo.engine import FRAME, Denoiser, process_array


def test_block_size_independent():
    rng = np.random.default_rng(0)
    x = (rng.standard_normal(48000) * 0.05).astype(np.float32)
    full = Denoiser().process(x)
    b = Denoiser()
    parts, i = [], 0
    for n in [100, 333, 480, 1000, 77, 2048]:
        parts.append(b.process(x[i:i + n]))
        i += n
    parts.append(b.process(x[i:]))
    assert np.allclose(full, np.concatenate(parts), atol=1e-4)


def test_output_length_matches_input():
    d = Denoiser()
    for n in (1, 479, 480, 481, 960):
        assert len(d.process(np.zeros(n, np.float32))) == n


def test_strength_zero_is_delayed_passthrough():
    rng = np.random.default_rng(1)
    x = (rng.standard_normal(9600) * 0.1).astype(np.float32)
    y = Denoiser(strength=0.0).process(x)
    assert np.allclose(y[FRAME:], x[:-FRAME], atol=2e-4)


def test_removes_steady_noise():
    rng = np.random.default_rng(2)
    x = (rng.standard_normal(48000 * 3) * 0.05).astype(np.float32)
    y = process_array(x)
    rms = lambda s: np.sqrt(np.mean(s ** 2))
    assert 20 * np.log10(rms(x[48000:]) / rms(y[48000:])) > 15
