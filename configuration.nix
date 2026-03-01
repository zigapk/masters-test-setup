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

  # isolate the cpu core 3 to perform testing on.
  boot.kernelParams = [ "isolcpus=3" ];
  hardware.enableAllFirmware = true;

  # bootloader.
  boot.loader.systemd-boot.enable = true;

  networking.hostname = hostname;
  networking.networkmanager.enable = true;

  # dynamicall linked executables support
  programs.nix-ld.enable = true;

  # set your time zone.
  time.timezone = "europe/ljubljana";

  # select internationalisation properties.
  i18n.defaultLocale = "en_us.utf-8";

  # caps to ctrl/escape remapping for convience
  services.keyd = {
    enable = true;

    keyboards = {
      default = {
        # apply to all keyboards
        ids = [ "*" ];

        settings = {
          main = {
            # maps capslock → esc when tapped, ctrl when held
            capslock = "overload(control, esc)";
          };
        };
      };
    };
  };

  # set zsh a default for all users
  programs.zsh = {
    enable = true;
    shellaliases = {
      vim = "nvim";
      cat = "bat";
      finit = "rm -rf .envrc .direnv && echo \"use flake\" >> .envrc && direnv allow";
      v = "nvim .";
    };
    interactiveShellInit = ''
      zsh_disable_compfix=true
      export EDITOR=nvim
      export VISUAL="nvim"
      export BAT_THEME="dracula"
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

  users.defaultusershell = pkgs.zsh;

  # add a group for realtime privileges
  users.groups.realtime = { };

  # grant the 'realtime' group the ability to request maximum
  # cpu priority (99) and lock memory (prevents the os from
  # swapping your robot's memory to disk, which causes latency).
  security.pam.loginlimits = [
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

  # define a user account
  users.users.zigapk = {
    isnormaluser = true;
    description = "žiga patačko koderman";
    extragroups = [
      "dialout"
      "networkmanager"
      "wheel"
      "realtime"
    ];
    openssh.authorizedkeys.keys = [
      "ssh-ed25519 aaaac3nzac1lzdi1nte5aaaaig5r1mt9pllx7ca8f6zvzskrp/k9spvsrsbensnyumry"
    ];
  };

  # list packages installed in system profile. to search, run:
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
    enablezshintegration = false;
    enablebashintegration = false;
  };

  # enable the openssh daemon.
  services.openssh = {
    enable = true;
    settings = {
      passwordauthentication = false;
      permitrootlogin = "no";
    };
  };
  system.stateversion = "25.05";

  networking.firewall.allowedTCPPorts = [
    22
    8000
  ];
}
