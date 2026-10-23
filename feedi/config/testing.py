ENV = "testing"
SECRET_KEY = b"\xffN\xcfX\xbc\xa9V\x8b*_zFB\xb9\xfa\x1d"
TESTING = True
SQLALCHEMY_DATABASE_URI = "sqlite:///feedi.test.db"

# mocket (used by the test suite) "resolves" mocked hostnames to the hostname itself, which the
# real SSRF guard would refuse. Disable it under testing only.
DISABLE_SSRF_GUARD = True
