import Cairo from 'gi://cairo';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const REFRESH_SECONDS = 300;
const RAYS = 12;

function ringColor(percent) {
    if (percent >= 50)
        return [0.18, 0.80, 0.44];
    if (percent >= 20)
        return [0.95, 0.67, 0.13];
    return [0.91, 0.25, 0.20];
}

const UsageRing = GObject.registerClass(class UsageRing extends St.Widget {
    _init(percent, muted = false) {
        super._init({
            style_class: 'clax-ring',
            layout_manager: new Clutter.BinLayout(),
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._percent = Math.max(0, Math.min(100, percent));
        this._muted = muted;

        this._canvas = new St.DrawingArea({x_expand: true, y_expand: true});
        this._canvas.connect('repaint', area => this._draw(area));
        this.add_child(this._canvas);

        this.add_child(new St.Label({
            text: `${this._percent}`,
            style_class: 'clax-ring-label',
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        }));
    }

    _draw(area) {
        // Raios no estilo da "faísca" do Claude em vez de um anel contínuo.
        const cr = area.get_context();
        const [width, height] = area.get_surface_size();
        const outer = Math.min(width, height) / 2 - 1.5;
        const centerX = width / 2;
        const centerY = height / 2;
        const lit = Math.round(RAYS * this._percent / 100);
        const [red, green, blue] = this._muted
            ? [0.78, 0.78, 0.78]
            : ringColor(this._percent);

        cr.setLineWidth(2.2);
        cr.setLineCap(Cairo.LineCap.ROUND);
        for (let i = 0; i < RAYS; i++) {
            const angle = -Math.PI / 2 + Math.PI * 2 * i / RAYS;
            const inner = outer - (i % 2 === 0 ? 4.5 : 3);
            if (i < lit)
                cr.setSourceRGBA(red, green, blue, 1);
            else if (this._muted)
                cr.setSourceRGBA(0.35, 0.35, 0.35, 0.85);
            else
                cr.setSourceRGBA(0.85, 0.47, 0.34, 0.55);
            cr.moveTo(centerX + inner * Math.cos(angle), centerY + inner * Math.sin(angle));
            cr.lineTo(centerX + outer * Math.cos(angle), centerY + outer * Math.sin(angle));
            cr.stroke();
        }
        cr.$dispose();
    }
});

const ClaxIndicator = GObject.registerClass(class ClaxIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'CLAX 5h Rings');
        this._box = new St.BoxLayout({style_class: 'clax-rings-box'});
        this.add_child(this._box);
        this._refreshId = 0;
        this._refresh();
        this._refreshId = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT, REFRESH_SECONDS, () => {
                this._refresh();
                return GLib.SOURCE_CONTINUE;
            });
    }

    _refresh() {
        const installedLauncher = GLib.build_filenamev([
            GLib.get_home_dir(), '.local', 'bin', 'clax',
        ]);
        const launcher = GLib.file_test(installedLauncher, GLib.FileTest.IS_EXECUTABLE)
            ? installedLauncher
            : GLib.find_program_in_path('clax');
        if (!launcher) {
            this._render([], 'Comando clax não encontrado');
            return;
        }

        const proc = new Gio.Subprocess({
            argv: [launcher, 'bar-data'],
            flags: Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
        });
        proc.init(null);
        proc.communicate_utf8_async(null, null, (source, result) => {
            try {
                const [, stdout] = source.communicate_utf8_finish(result);
                const accounts = stdout.trim().split('\n').filter(Boolean).map(line => {
                    const [number, email, percent, reset, weeklyPercent] = line.split('\t');
                    return {
                        number,
                        email,
                        percent: Number(percent),
                        reset,
                        weeklyPercent: Number(weeklyPercent),
                    };
                }).filter(account => Number.isFinite(account.percent));
                this._render(accounts, null);
            } catch (error) {
                logError(error, 'Falha ao atualizar CLAX 5h Rings');
                this._render([], 'Limites indisponíveis');
            }
        });
    }

    _render(accounts, error) {
        this._box.destroy_all_children();
        this.menu.removeAll();

        if (accounts.length === 0) {
            this._box.add_child(new St.Label({
                text: 'CLAX',
                style_class: 'clax-empty-label',
                y_align: Clutter.ActorAlign.CENTER,
            }));
            this.menu.addMenuItem(new PopupMenu.PopupMenuItem(
                error ?? 'Nenhuma conta conectada', {reactive: false}));
        } else {
            for (const account of accounts) {
                const weeklyExhausted = account.percent > 0 && account.weeklyPercent === 0;
                const ring = new UsageRing(account.percent, weeklyExhausted);
                if (weeklyExhausted)
                    ring.opacity = 150;
                ring.accessible_name = weeklyExhausted
                    ? `Conta ${account.number}: ${account.percent}% nas 5 horas, limite semanal esgotado`
                    : `Conta ${account.number}: ${account.percent}%`;
                this._box.add_child(ring);
                const weeklyStatus = account.weeklyPercent >= 0
                    ? `semana ${account.weeklyPercent}%`
                    : 'semana indisponível';
                const blockedStatus = weeklyExhausted ? ' · bloqueado' : '';
                this.menu.addMenuItem(new PopupMenu.PopupMenuItem(
                    `Conta ${account.number} · ${account.email} · 5h ${account.percent}% · ${weeklyStatus} · ${account.reset}${blockedStatus}`,
                    {reactive: false}));
            }
        }

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        const refresh = new PopupMenu.PopupMenuItem('Atualizar agora');
        refresh.connect('activate', () => this._refresh());
        this.menu.addMenuItem(refresh);
    }

    destroy() {
        if (this._refreshId) {
            GLib.source_remove(this._refreshId);
            this._refreshId = 0;
        }
        super.destroy();
    }
});

export default class ClaxRingsExtension extends Extension {
    enable() {
        this._indicator = new ClaxIndicator();
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
