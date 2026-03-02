{
  buildPythonPackage,
  lib,
  pytestCheckHook,
  python-dotenv,
  setproctitle,
  setuptools,
}:
buildPythonPackage {
  name = "git-cuttle";
  src = lib.cleanSource ./.;
  pyproject = true;

  nativeBuildInputs = [ setuptools ];

  propagatedBuildInputs = [
    python-dotenv
    setproctitle
  ];

  nativeCheckInputs = [
    pytestCheckHook
  ];

  # Skip integration tests during build (they require the installed executable)
  pytestFlagsArray = [ "-m 'not integration'" ];

  # pythonImportsCheck = [ "git_cuttle" ];

  meta = {
    mainProgram = "gitcuttle";
    # description = "A short description of my application";
    # homepage = "https://github.com";
    # license = lib.licenses.mit;
  };
}
