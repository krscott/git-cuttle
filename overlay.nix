final: prev: {
  python3 = prev.python3.override {
    packageOverrides = _: _: {
      git-cuttle = prev.python3.pkgs.callPackage ./default.nix { };
    };
  };

  python3Packages = final.python3.pkgs;

  git-cuttle = prev.python3.pkgs.toPythonApplication final.python3.pkgs.git-cuttle;
}
