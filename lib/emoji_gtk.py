#!/usr/bin/env python3

import os
import sys
import json
from collections import OrderedDict, deque
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, AppIndicator3, Gdk, GdkPixbuf
import emoji_shared as shared
import emoji_lib as lib
import timeit


class Indicator(object):

	def __init__(self):

		self.indicator = AppIndicator3.Indicator.new(
			'emoji-keyboard',
			shared.icon,
			AppIndicator3.IndicatorCategory.APPLICATION_STATUS)
		self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
		self.indicator.set_menu(self.build_menu())
		self.indicator.set_secondary_activate_target(self.show_keyboard)
		Gtk.main()

	def build_menu(self):

		menu = Gtk.Menu()
		self.show_keyboard = Gtk.ImageMenuItem('Show Keyboard')
		icon_keyboard = Gtk.Image.new_from_icon_name('keyboard', 22)
		self.show_keyboard.set_image(icon_keyboard)
		self.show_keyboard.connect('activate', self.toggle_keyboard)
		self.search = Gtk.ImageMenuItem('Search')
		icon_search = Gtk.Image.new_from_icon_name('search', 22)
		self.search.set_image(icon_search)
		self.search.connect('activate', self.toggle_search)
		self.settings = Gtk.ImageMenuItem('Settings')
		icon_settings = Gtk.Image.new_from_icon_name('configure', 22)
		self.settings.set_image(icon_settings)
		self.settings.connect('activate', self.show_settings)
		menu_quit = Gtk.ImageMenuItem('Quit')
		icon_quit = Gtk.Image.new_from_icon_name('application-exit', 22)
		menu_quit.set_image(icon_quit)
		menu_quit.connect('activate', self.quit)
		menu.append(self.show_keyboard)
		menu.append(self.search)
		menu.append(self.settings)
		menu.append(menu_quit)
		menu.show_all()
		return menu

	def quit(self, menu_item):

		Gtk.main_quit()
		#~ exit_()
		sys.exit(0)

	def toggle_keyboard(self, menu_item):

		if shared.keyboard_visible:
			shared.keyboard.close()
		else:
			shared.keyboard.show_all()

	def toggle_search(self, menu_item):

		if shared.search_visible:
			shared.search.close()
		else:
			shared.search.show_all()

	def show_settings(self, menu_item):

		shared.prefs.show_all()


class Emoji(object):

	def __init__(self):

		model = self.load_emoji()
		self.tone_filter = model.filter_new()
		self.tone_filter.set_visible_func(self.filter_tone, None)
		self.categories = self.get_categories_filter()
		self.sorted_short = self.tone_filter.sort_new_with_model()
		self.sorted_short.set_sort_column_id(1, Gtk.SortType.ASCENDING)
		self.sorted_full = self.tone_filter.sort_new_with_model()
		self.sorted_full.set_sort_column_id(4, Gtk.SortType.ASCENDING)

		self.suggestion_iters = []
		self.previous_key = ''

	def load_emoji(self):

		with open(os.path.join(shared.data_dir, 'emoji.json')) as emoji_json:
			emoji_raw = json.loads(
				emoji_json.read(), object_pairs_hook=OrderedDict)

		model = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, str, str)
		base_props = {}
		for emoji in emoji_raw:
			category = emoji_raw[emoji]['category']
			codepoint = emoji_raw[emoji]['unicode']
			if codepoint in shared.emoji_modifier_base:
				base_props[codepoint] = emoji_raw[emoji]
			if '-' in codepoint:
				main_codepoint = codepoint.split('-')[0]
				if main_codepoint in shared.emoji_modifier_base:
					shortname = base_props[main_codepoint]['shortname']
					description = (base_props[main_codepoint]['name']
									+ '. Keywords:'
									+ ' '.join(
										base_props[main_codepoint]['keywords']))
				else:
					shortname = emoji_raw[emoji]['shortname']
					description = (emoji_raw[emoji]['name']
									+ '. Keywords: '
									+ ' '.join(emoji_raw[emoji]['keywords']))
			else:
				shortname = emoji_raw[emoji]['shortname']
				description = (emoji_raw[emoji]['name']
								+ '. Keywords: '
								+ ' '.join(emoji_raw[emoji]['keywords']))
			pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
				os.path.join(shared.data_dir, 'svg', codepoint + '.svg'),
				shared.settings['emoji_size'],
				shared.settings['emoji_size'],
				True)
			model.append(
				[pixbuf, shortname, category, codepoint, description])
		return model

	def filter_tone(self, model, tree_iter, udata):

		codepoint = model[tree_iter][3]
		sequence = codepoint.split('-')
		if sequence[0] in shared.emoji_modifier_base:
			if shared.settings['tone']:
				if len(sequence) > 1 and sequence[1] == shared.settings['tone']:
					return True
				else:
					return False
			elif len(sequence) > 1:
				return False
			else:
				return True
		elif sequence[0] in shared.emoji_modifiers:
			return False
		else:
			return True

	def filter_category(self, model, tree_iter, udata_category):

		category = model[tree_iter][2]
		if category == udata_category:
			return True
		else:
			return False

	def get_categories_filter(self):

		categories = {}
		for category in shared.categories:
			if category != 'recent':
				categories[category] = self.tone_filter.filter_new()
				categories[category].set_visible_func(
					self.filter_category, category)
			else:
				recent_filter = self.tone_filter.filter_new()
				recent_filter.set_visible_func(self.filter_recent, None)
				categories[category] = recent_filter.sort_new_with_model()
				categories[category].set_sort_func(1, self.sort_recent, None)
				categories[category].set_sort_column_id(
					1, Gtk.SortType.ASCENDING)
		return categories

	def filter_recent(self, model, tree_iter, udata):

		shortname = model[tree_iter][1]
		if shortname in shared.recent:
			return True
		else:
			return False

	def sort_recent(self, model, a_iter, b_iter, udata):

		a_shortname = model[a_iter][1]
		b_shortname = model[b_iter][1]
		return (shared.recent.index(a_shortname)
			- shared.recent.index(b_shortname))

	def match_full(self, completion, key, tree_iter, udata):

		model = completion.get_model()
		matches = (True if key in model[tree_iter][4] else False
			for key in key.split())
		result = all(matches)
		if key != self.previous_key:
			self.suggestion_iters = []
		if result:
			self.suggestion_iters.append(tree_iter)
		self.previous_key = key
		return result

	def sort_full(self, model, a_iter, b_iter, udata_key):

		keys = udata_key.split()
		a_string = model[a_iter][4]
		b_string = model[b_iter][4]
		if keys:
			a_score = sum(a_string.find(key) for key in keys) / len(keys)
			b_score = sum(b_string.find(key) for key in keys) / len(keys)
			return a_score - b_score
		else:
			return 0


class Keyboard(Gtk.Window):

	def __init__(self):

		Gtk.Window.__init__(
			self, title='Pick emoji',
			accept_focus=False,
			skip_taskbar_hint=True)
		self.set_keep_above(True)
		self.set_icon_name(shared.icon)
		self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
		self.set_border_width(6)
		if shared.settings['keyboard_use_compact']:
			self.set_default_size(*shared.settings['keyboard_size_compact'])
		else:
			self.set_default_size(*shared.settings['keyboard_size_full'])
		self.connect('show', self.window_shown)
		self.connect('delete-event', self.hide_window)
		self.connect('configure-event', self.window_resized)

		self.notebook = Gtk.Notebook()
		self.add(self.notebook)

		self.emoji_views = []
		for category in shared.categories:
			scrolled_window = Gtk.ScrolledWindow()
			model = shared.emoji.categories[category]
			page = Gtk.IconView.new_with_model(model)
			page.set_selection_mode(Gtk.SelectionMode.NONE)
			page.set_activate_on_single_click(True)
			page.connect('item-activated', self.paste_emoji)
			page.set_pixbuf_column(0)
			page.set_tooltip_column(1)
			self.emoji_views.append(page)
			scrolled_window.add(page)
			label = Gtk.Box(spacing=2)
			pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(os.path.join(
				shared.data_dir,
				'category_icons',
				shared.categories[category] + '.svg'),
				16, 16, True)
			image = Gtk.Image.new_from_pixbuf(pixbuf)
			text = Gtk.Label(shared.categories[category].title())
			label.pack_start(image, True, True, 0)
			label.pack_start(text, True, True, 0)
			image.show()
			if shared.settings['keyboard_use_compact']:
				page.set_columns(shared.settings['keyboard_columns_compact'])
			else:
				page.set_columns(shared.settings['keyboard_columns_full'])
				text.show()
			self.notebook.append_page(scrolled_window, label)

	def window_shown(self, window):

		self.move(*shared.settings['keyboard_pos'])
		shared.keyboard_visible = True
		return False

	def hide_window(self, window, event):

		self.hide()
		shared.keyboard_visible = False
		return True

	def window_resized(self, window, event):

		shared.settings['keyboard_pos'] = (event.x, event.y)
		padding = self.emoji_views[1].get_item_padding() * 2
		spacing = self.emoji_views[1].get_column_spacing()
		column = shared.settings['emoji_size'] + padding + spacing
		columns = event.width // column
		if shared.settings['keyboard_use_compact']:
			shared.settings['keyboard_size_compact'] = (event.width, event.height)
			shared.settings['keyboard_columns_compact'] = columns
		else:
			shared.settings['keyboard_size_full'] = (event.width, event.height)
			shared.settings['keyboard_columns_full'] = columns
		for iconview in self.emoji_views:
			iconview.set_columns(columns)

	def paste_emoji(self, widget, path):

		model = widget.get_model()
		shortname = model[path][1]
		codepoint = model[path][3]

		if '-' in codepoint:
			sequence = codepoint.split('-')
			string = chr(int(sequence[0], 16)) + chr(int(sequence[1], 16))
		else:
			string = chr(int(codepoint, 16))
		shared.clipboard.paste(string)

		if shortname in shared.recent:
			shared.recent.remove(shortname)
		shared.recent.appendleft(shortname)
		shared.emoji.categories['recent'].get_model().refilter()
		# Need to trigger resort when emoji already in recent gets used again
		shared.emoji.categories['recent'].set_sort_func(
			1, shared.emoji.sort_recent, None)


class Search(Gtk.Window):

	def __init__(self):

		Gtk.Window.__init__(self, title='Search emoji', skip_taskbar_hint=True)
		self.set_keep_above(True)
		self.set_resizable(False)
		self.set_icon_name(shared.icon)
		self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
		self.set_default_size(250, 45)
		self.set_border_width(6)
		self.connect('show', self.window_shown)
		self.connect('delete-event', self.hide_window)
		self.connect('configure-event', self.window_moved)

		self.entry = Gtk.Entry()
		self.add(self.entry)
		self.full_completer = Gtk.EntryCompletion()
		self.entry.set_completion(self.full_completer)
		self.full_completer.set_model(shared.emoji.sorted_full)
		full_pixbuf_cell = Gtk.CellRendererPixbuf()
		self.full_completer.pack_start(full_pixbuf_cell, False)
		self.full_completer.add_attribute(full_pixbuf_cell, 'pixbuf', 0)
		self.full_completer.set_text_column(4)
		self.full_completer.set_match_func(shared.emoji.match_full, None)

		self.short_completer = Gtk.EntryCompletion()
		self.short_completer.set_model(shared.emoji.sorted_short)
		short_pixbuf_cell = Gtk.CellRendererPixbuf()
		self.short_completer.pack_start(short_pixbuf_cell, False)
		self.short_completer.add_attribute(short_pixbuf_cell, 'pixbuf', 0)
		self.short_completer.set_text_column(1)

		self.entry.connect('changed', self.set_model)
		self.entry.connect('activate', self.select_first)
		self.full_completer.connect('match-selected', self.paste_emoji)
		self.short_completer.connect('match-selected', self.paste_emoji)
		self.full_completer.connect('cursor-on-match', self.paste_emoji)
		self.short_completer.connect('cursor-on-match', self.paste_emoji)

	def window_shown(self, window):

		self.move(*shared.settings['search_pos'])
		shared.search_visible = True
		return False

	def hide_window(self, window, event):

		self.hide()
		shared.search_visible = False
		return True

	def window_moved(self, window, event):

		shared.settings['search_pos'] = (event.x, event.y)

	def set_model(self, entry):

		key = entry.get_text()
		if key.startswith(':'):
			entry.set_completion(self.short_completer)
		else:
			shared.emoji.sorted_full.set_sort_func(
				4, shared.emoji.sort_full, key)
			entry.set_completion(self.full_completer)

	def select_first(self, entry):

		if entry.get_text():
				completer = entry.get_completion()
				model = completer.get_model()
				tree_iter = shared.emoji.suggestion_iters[0]
				self.paste_emoji(completer, model, tree_iter)

	def paste_emoji(self, completer, model, tree_iter):

		string = []
		codepoint = model[tree_iter][3]
		if '-' in codepoint:
			for char in codepoint.split('-'):
				string.append(chr(int(char, 16)))
		else:
			string.append(chr(int(codepoint, 16)))
		self.entry.set_text('')
		# When selecting match with mouse window.close() doesn't seem to work
		self.hide_window(self, None)
		shared.clipboard.paste(''.join(string))
		return True


class Preferences(Gtk.Window):

	def __init__(self):

		Gtk.Window.__init__(self, title='Preferences')
		self.set_icon_name(shared.icon)
		self.set_border_width(6)
		self.connect('delete-event', self.hide_window)

		grid = Gtk.Grid(column_spacing=6, row_spacing=6)
		self.add(grid)

		autostart_label = Gtk.Label('Run on login:')
		grid.attach(autostart_label, 1, 0, 2, 1)
		autostart_switch = Gtk.Switch()
		autostart_switch.set_active(shared.manager.check_autostart())
		autostart_switch.connect('notify::active', self.set_autostart)
		grid.attach(autostart_switch, 4, 0, 3, 1)

		tone_label = Gtk.Label('Select skin tone for people emoji*:')
		grid.attach(tone_label, 1, 1, 5, 1)
		previous_button = None
		for modifier in shared.emoji_modifiers:
			button = Gtk.RadioButton.new_from_widget(previous_button)
			button.set_mode(False)
			if modifier:
				pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
					os.path.join(shared.data_dir, 'svg', modifier + '.svg'),
					24, 24,
					True)
				# Abusing name property to store data. Does make for clean code.
				button.set_name(modifier)
			else:
				pixbuf = GdkPixbuf.Pixbuf.new(
					GdkPixbuf.Colorspace.RGB, True, 8, 24, 24)
				pixbuf.fill(0)
				button.set_name('')
			image = Gtk.Image.new_from_pixbuf(pixbuf)
			button.set_image(image)
			if modifier == shared.settings['tone']:
				button.set_active(True)
			button.connect('toggled', self.set_emoji_tone)
			if previous_button:
				grid.attach_next_to(button, previous_button, 1, 1, 1)
			else:
				grid.attach(button, 1, 2, 1, 1)
			previous_button = button

		size_label = Gtk.Label('Emoji size*:')
		grid.attach(size_label, 1, 3, 2, 1)
		adjustment = Gtk.Adjustment(32, 16, 64, 1, 16, 0)
		size_spinner = Gtk.SpinButton()
		size_spinner.set_adjustment(adjustment)
		size_spinner.set_numeric(True)
		size_spinner.set_digits(0)
		size_spinner.set_value(shared.settings['emoji_size'])
		size_spinner.connect('value-changed', self.set_emoji_size)
		grid.attach(size_spinner, 4, 3, 3, 1)

		layout_label = Gtk.Label('Use compact layout*:')
		grid.attach(layout_label, 1, 4, 3, 1)
		layout_switch = Gtk.Switch()
		layout_switch.set_active(shared.settings['keyboard_use_compact'])
		layout_switch.connect('notify::active', self.set_keyboard_layout)
		grid.attach(layout_switch, 4, 4, 3, 1)

		warning_label = Gtk.Label('* requires restart')
		grid.attach(warning_label, 1, 5, 3, 1)

	def hide_window(self, window, event):

		self.hide()
		shared.manager.save_settings()
		return True

	def set_autostart(self, widget, pspec):

		shared.manager.set_autostart(widget.get_active())

	def set_emoji_tone(self, button):

		tone = button.get_name()
		if tone:
			shared.settings['tone'] = tone
		else:
			shared.settings['tone'] = None

	def set_emoji_size(self, widget):

		shared.settings['emoji_size'] = widget.get_value_as_int()

	def set_keyboard_layout(self, widget, pspec):

		shared.settings['keyboard_use_compact'] = widget.get_active()


shared.manager = lib.Manager()
shared.prefs = Preferences()
shared.emoji = Emoji()
shared.clipboard = lib.Clipboard()
shared.keyboard = Keyboard()
shared.search = Search()
shared.indicator = Indicator()
