{
  pkgs,
  hostname,
  ...
}:
{
  nix.settings.experimental-features = [
    "nix-command"
    "flakes"
  ];
  boot.kernelPackages = pkgs.linuxPackages-rt_latest;

  # Isolate the CPU core 3 to perform testing on.
  boot.kernelParams = [ "isolcpus=3" ];
  hardware.enableAllFirmware = true;

  # Bootloader.
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  networking.hostName = hostname;
  networking.networkmanager.enable = true;

  # Dynamicall linked executables support
  programs.nix-ld.enable = true;

  # Set your time zone.
  time.timeZone = "Europe/Ljubljana";

  # Select internationalisation properties.
  i18n.defaultLocale = "en_US.UTF-8";

  # Caps to ctrl/escape remapping for convience
  services.keyd = {
    enable = true;

    keyboards = {
      default = {
        # Apply to all keyboards
        ids = [ "*" ];

        settings = {
          main = {
            # Maps CapsLock → Esc when tapped, Ctrl when held
            capslock = "overload(control, esc)";
          };
        };
      };
    };
  };

  # Set zsh a default for all users
  programs.zsh = {
    enable = true;
    shellAliases = {
      vim = "nvim";
      cat = "bat";
      finit = "rm -rf .envrc .direnv && echo \"use flake\" >> .envrc && direnv allow";
      v = "nvim .";
    };
    initContent = ''
      ZSH_DISABLE_COMPFIX=true
      export EDITOR=nvim
      export VISUAL="nvim"
      export BAT_THEME="Dracula"
      export LS_COLORS=$(vivid generate dracula)

      setopt appendhistory
      setopt sharehistory
      setopt hist_ignore_space
      setopt hist_ignore_all_dups
      setopt hist_save_no_dups
      setopt hist_ignore_dups
      setopt hist_find_no_dups

      zstyle ':fzf-tab:complete:cd:*' fzf-preview 'ls --color $realpath'
      zstyle ':fzf-tab:complete:__zoxide_z:*' fzf-preview 'ls --color $realpath'

      # Shell integrations
      eval "$(atuin init zsh --disable-up-arrow)"
      eval "$(direnv hook zsh)"
      eval "$(fzf --zsh)"
      eval "$(zoxide init --cmd cd zsh)"

    '';
    oh-my-zsh = {
      enable = true;
      plugins = [
        "git"
        "sudo"
      ];
    };
    plugins = [
      {
        # will source zsh-autosuggestions.plugin.zsh
        name = "zsh-autosuggestions";
        src = pkgs.zsh-autosuggestions;
        file = "share/zsh-autosuggestions/zsh-autosuggestions.zsh";
      }
      {
        name = "zsh-completions";
        src = pkgs.zsh-completions;
        file = "share/zsh-completions/zsh-completions.zsh";
      }
      {
        name = "zsh-syntax-highlighting";
        src = pkgs.zsh-syntax-highlighting;
        file = "share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh";
      }
      {
        name = "fzf-tab";
        src = pkgs.zsh-fzf-tab;
        file = "share/fzf-tab/fzf-tab.plugin.zsh";
      }
    ];
  };
  users.defaultUserShell = pkgs.zsh;

  # Add a group for realtime privileges
  users.groups.realtime = { };

  # Grant the 'realtime' group the ability to request maximum
  # CPU priority (99) and lock memory (prevents the OS from
  # swapping your robot's memory to disk, which causes latency).
  security.pam.loginLimits = [
    {
      domain = "@realtime";
      type = "-";
      item = "rtprio";
      value = "99";
    }
    {
      domain = "@realtime";
      type = "-";
      item = "memlock";
      value = "unlimited";
    }
  ];

  # Define a user account
  users.users.zigapk = {
    isNormalUser = true;
    description = "Žiga Patačko Koderman";
    extraGroups = [
      "dialout"
      "networkmanager"
      "wheel"
      "realtime"
    ];
    openssh.authorizedKeys.keys = [
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIG5r1Mt9pLlX7cA8F6ZVZSkrP/k9sPVSrSbeNSnyumrY"
    ];
  };

  # List packages installed in system profile. To search, run:
  environment.systemPackages = with pkgs; [
    git
    neovim
    pciutils
    killall
    lsof
    usbutils
    gnupg
    openssl
    python314
    fzf
    vivid
    zoxide
    atuin
    direnv
    eza
    tree
    ripgrep
    jq
    bat
    lazygit
  ];

  programs.nix-index = {
    enable = true;
    enableZshIntegration = false;
    enableBashIntegration = false;
  };

  # Enable the OpenSSH daemon.
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      PermitRootLogin = "no";
    };
  };
  system.stateVersion = "25.05";

  networking.firewall.allowedTCPPorts = [
    22
    8000
  ];
}
