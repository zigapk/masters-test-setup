{
  description = "Nix flake for realtime testing of zigapk/hertz library.";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
    flake-utils.url = "github:numtide/flake-utils";
    nix-index-database = {
      url = "github:nix-community/nix-index-database";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nixos-hardware.url = "github:NixOS/nixos-hardware/master";
  };

  outputs =
    {
      nixpkgs,
      flake-utils,
      nix-index-database,
      nixos-hardware,
      ...
    }@inputs:
    let
      username = "zigapk";
    in
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };
        nativeBuildInputs = with pkgs; [
          nodejs_22
          corepack_22
          go
          python314
          xvfb-run
        ];
        buildInputs = [ ];
      in
      {
        devShells.default = pkgs.mkShell {
          inherit buildInputs nativeBuildInputs;
          # Dynamically link the C++ libraries required by pre-compiled Python wheels
          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath (
            with pkgs;
            [
              stdenv.cc.cc.lib
              zlib
            ]
          );
        };
      }
    )
    // {
      nixosConfigurations.hertz = nixpkgs.lib.nixosSystem {
        system = "x86_64-linux";
        specialArgs = {
          homeDirectory = "/home/${username}";
          hostname = "hertz";
          inherit
            inputs
            username
            nix-index-database
            ;
        };
        modules = [
          ./nix/hardware-configuration.nix
          ./nix/configuration.nix
        ];
      };
    };
}
