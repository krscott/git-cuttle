{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    let
      supportedSystems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
    in
    flake-utils.lib.eachSystem supportedSystems (
      system:
      let
        localOverlay = import ./overlay.nix;

        pkgs = import nixpkgs {
          inherit system;
          overlays = [ localOverlay ];
        };

        pythonDev = pkgs.python3.pkgs.git-cuttle.pythonModule.withPackages (
          ps:
          with ps;
          [
            black
            isort
            mypy
            pytest
          ]
          ++ pkgs.git-cuttle.propagatedBuildInputs
          ++ pkgs.git-cuttle.nativeBuildInputs
        );

        mkApp = text: {
          type = "app";
          program = pkgs.lib.getExe (
            pkgs.writeShellApplication {
              name = "app";
              runtimeInputs = [ pythonDev ];
              inherit text;
            }
          );
        };
      in
      {
        packages = {
          inherit (pkgs) git-cuttle;
          default = pkgs.git-cuttle;
        };

        devShells = {
          default = pkgs.mkShell {
            inputsFrom = [ pkgs.git-cuttle ];
            nativeBuildInputs = [
              pythonDev
              pkgs.pyright
              pkgs.nodejs
            ];
            packages = [ pkgs.python3.pkgs.venvShellHook ];
            venvDir = ".venv";
            postVenvCreation = ''
              pip install -e '.[dev]'
            '';
            shellHook = ''
              runHook venvShellHook
              export PYTHONPATH="''${PYTHONPATH:-}:."
              if [ ! -f CLAUDE.md ]; then
                ln -s AGENTS.md CLAUDE.md
              fi
            '';
          };
        };

        apps = {
          format = mkApp ''
            ./format.sh
          '';

          mypy = mkApp ''
            mypy . "$@"
          '';
        };

        formatter = pkgs.nixfmt;
      }
    );
}
