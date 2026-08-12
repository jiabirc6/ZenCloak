from zencloak.core.secrets import decrypt_text, encrypt_text


def test_encrypt_decrypt_roundtrip():
    encrypted = encrypt_text("my-proxy-password")
    assert encrypted != "my-proxy-password"
    assert decrypt_text(encrypted) == "my-proxy-password"
