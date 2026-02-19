{
  buildPythonPackage,
  lib,
  setuptools,
}:
buildPythonPackage {
  name = "git-cuttle";
  src = lib.cleanSource ./.;
  pyproject = true;

  nativeBuildInputs = [ setuptools ];

  propagatedBuildInputs = [ ];

  doCheck = false;

  # pythonImportsCheck = [ "git_cuttle" ];

  meta = {
    mainProgram = "gitcuttle";
    # description = "A short description of my application";
    # homepage = "https://github.com";
    # license = lib.licenses.mit;
  };
}
