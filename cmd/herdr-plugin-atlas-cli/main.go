package main

import (
	"context"
	"fmt"
	"os"

	"github.com/masonhuemmer/herdr-plugin-atlas-cli/internal/plugin"
)

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintf(os.Stderr, "%s: %v\n", plugin.PluginID, err)
		os.Exit(1)
	}
}

func run(args []string) error {
	if len(args) != 1 {
		return fmt.Errorf("usage: herdr-plugin-atlas-cli <startup|reconcile|refresh|open-picker|picker|open-status|status|open-detail|detail|open-draft|draft|install>")
	}
	env := plugin.EnvMap()
	if args[0] == "install" {
		return plugin.Install(env, os.Stdout)
	}
	app, err := plugin.NewApp(env, nil)
	if err != nil {
		return err
	}
	ctx := context.Background()
	screen := plugin.NewScreen(os.Stdin, os.Stdout)
	switch args[0] {
	case "startup":
		return app.Start(ctx)
	case "reconcile":
		return app.Sync(ctx, false)
	case "refresh":
		return app.Sync(ctx, true)
	case "open-picker":
		return app.OpenAction(ctx, "picker")
	case "picker":
		defer screen.Wait()
		return app.Pick(ctx, screen)
	case "open-status":
		return app.OpenAction(ctx, "status")
	case "status":
		defer screen.Wait()
		return app.TransitionMenu(ctx, screen)
	case "open-detail":
		return app.OpenAction(ctx, "detail")
	case "detail":
		return app.Detail(ctx, screen)
	case "open-draft":
		return app.OpenAction(ctx, "draft")
	case "draft":
		defer screen.Wait()
		return app.Draft(ctx, screen)
	default:
		return fmt.Errorf("unknown command %q", args[0])
	}
}
