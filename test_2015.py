import datetime
import json
import re
from collections import defaultdict
from dateutil.relativedelta import relativedelta

from renderers import HighchartRenderer, TableRenderer
from wxparser import Parser, UserData, Category, _slugify


class CST(datetime.tzinfo):

    def utcoffset(self, dt):
        return datetime.timedelta(hours=8)

    def tzname(self, dt):
        return 'Beijing Time'

    def dst(self, dt):
        return datetime.timedelta(hours=8)


beijing_time = CST()
beginning_of_2015 = datetime.datetime(2015, 1, 1, 0, 0, 0, 0, beijing_time)
beginning_of_2016 = datetime.datetime(2016, 1, 1, 0, 0, 0, 0, beijing_time)
beginning_of_2017 = datetime.datetime(2017, 1, 1, 0, 0, 0, 0, beijing_time)

contrasty_colors = ['#e41a1c', '#377eb8', '#4daf4a', '#984ea3', '#ff7f00', '#ffff33', '#a65628', '#f781bf', '#999999']
contrasty_colors_rgba = [
    'rgba(228, 26, 28, 0.6)',
    'rgba(55, 126, 184, 0.6)',
    'rgba(77, 175, 74, 0.6)',
    'rgba(152, 78, 163, 0.6)',
    'rgba(255, 127, 0, 0.6)',
    'rgba(255, 255, 51, 0.6)',
    'rgba(166, 86, 40, 0.6)',
    'rgba(247, 129, 191, 0.6)',
    'rgba(153, 153, 153, 0.6)'
]


def build_sent_by_category_by_month_graph(wxp):
    # Build the timespans
    timespans = []
    rolling_date = datetime.datetime(2015, 1, 1, 0, 0, 0, 0, beijing_time)
    while rolling_date < beginning_of_2016:
        next_start = rolling_date + relativedelta(months=1)
        timespans.append((rolling_date, next_start))
        rolling_date = next_start

    raw_data = defaultdict(lambda: [0] * len(timespans))
    for thread in wxp.individual_threads:
        category_slug = thread.category.slug if getattr(thread, 'category', None) else 'other'
        for i in xrange(0, len(timespans)):
            from_timestamp, to_timestamp = timespans[i]
            raw_data[category_slug][i] += len(filter(lambda message: message.sent and message.timestamp >= from_timestamp and message.timestamp < to_timestamp, thread.messages))

    for thread in wxp.group_threads:
        for i in xrange(0, len(timespans)):
            from_timestamp, to_timestamp = timespans[i]
            raw_data['group-chats'][i] += len(filter(lambda message: message.sent and message.timestamp >= from_timestamp and message.timestamp < to_timestamp, thread.messages))

    sorted_keys = list(reversed(sorted(raw_data.keys(), key=lambda slug: sum(raw_data[slug]))))

    series_data = []
    for series in sorted_keys:
        series_data.append({
            'name': series,
            'data': raw_data[series],
        })

    return {
        'chart': {
            'type': 'area'
        },
        'title': {
            'text': 'Messages sent'
        },
        'subtitle': {
            'text': 'per month, by category'
        },
        'colors': ['#e41a1c', '#377eb8', '#4daf4a', '#984ea3', '#ff7f00', '#ffff33', '#a65628', '#f781bf', '#999999'],
        'xAxis': {
            'categories': [timespan[0].strftime('%Y-%m') for timespan in timespans],
            'tickmarkPlacement': 'on',
            'title': {
                'enabled': False,
            },
        },
        'yAxis': {
            'title': {
                'text': 'Messages sent'
            },
        },
        'tooltip': {
            'shared': True,
            'valueSuffix': ' messages'
        },
        'plotOptions': {
            'area': {
                'stacking': 'normal',
                'lineWidth': 1,
            }
        },
        'series': series_data,
    }


class ScatterPlotSeries(object):

    def __init__(self, name, thread_filter, message_filter, color):
        self.name = name
        self.thread_filter = thread_filter
        self.message_filter = message_filter
        self.color = color


def build_message_scatterplot(wxp, title, series_list):

    def _day_of_year(timestamp):
        return int((timestamp - beginning_of_2015).total_seconds() / (60 * 60 * 24))

    def _hour_of_day(timestamp):
        return round(timestamp.hour + (timestamp.minute / 60.0), 2)

    series_output = []
    for series in series_list:
        # Start with the blank structure
        series_output.append({
            'name': series.name,
            'color': series.color,
            'data': [],
        })
        for thread in filter(series.thread_filter, wxp.threads):
            for message in filter(series.message_filter, filter(lambda message: message.timestamp >= beginning_of_2015 and message.timestamp < beginning_of_2016, thread.messages)):
                series_output[-1]['data'].append([_day_of_year(message.timestamp.astimezone(beijing_time)), _hour_of_day(message.timestamp.astimezone(beijing_time))])

    return {
        'chart': {
            'type': 'scatter',
            'zoomType': 'xy',
        },
        'title': {
            'text': title,
        },
        'xAxis': {
            'title': {
                'enabled': True,
                'text': 'Day of Year',
            },
            'tickPositions': [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365],
            # 'startOnTick': True,
            # 'endOnTick': True,
            # 'showLastLabel': True,
        },
        'yAxis': {
            'title': {
                'text': 'Hour of Day (China Standard Time)',
            },
            'min': 0,
            'max': 24,
            'tickPositions': [0, 4, 8, 12, 16, 20, 24],
        },
        'plotOptions': {
            'scatter': {
                'marker': {
                    'radius': 3,
                },
            },
        },
        'series': series_output,
    }


def build_sent_message_by_category_scatterplot(wxp, userdata):
    class NullCategory(object):
        slug = 'other'

    def _thread_filter_generator(slug):
        return lambda thread: getattr(thread, 'category', NullCategory()).slug == slug

    i = 0
    series_list = []
    for category in sorted(filter(lambda key: key != 'other', userdata.categories.keys()), key=lambda key: userdata.categories[key].display_name):
        series_list.append(ScatterPlotSeries(userdata.categories[category].display_name,
                                             _thread_filter_generator(category),
                                             lambda message: message.sent,
                                             contrasty_colors_rgba[i]))
        i += 1

    series_list.append(ScatterPlotSeries('Group Chats',
                                         lambda thread: thread.is_group_chat,
                                         lambda message: message.sent,
                                         contrasty_colors_rgba[i]))
    i += 1

    series_list.append(ScatterPlotSeries('Other',
                                         _thread_filter_generator('other'),
                                         lambda message: message.sent,
                                         contrasty_colors_rgba[i]))
    i += 1

    return build_message_scatterplot(wxp, '2015 - All Sent Messages', series_list)


def _group_chat_alias(original_display_name):
        try:
            return json.loads(open('group_chat_aliases.json', 'r').read()).get(original_display_name, original_display_name)
        except (IOError, ValueError):
            return original_display_name


def build_group_chat_ranking_table(wxp):
    group_chat_ranking = []
    for thread in list(reversed(sorted(wxp.group_threads, key=lambda thread: len(_sent_chats_in_2015(thread))))):
        display_name = _group_chat_alias(thread.contact.display_name)
        if not display_name:
            continue
        my_sent = len(_sent_chats_in_2015(thread))
        total_sent = len(_chats_in_2015(thread))
        percent = round(100.0 * my_sent / total_sent, 1)
        group_chat_ranking.append((display_name, _int_with_comma(my_sent), _int_with_comma(total_sent), percent))
        if len(group_chat_ranking) == 8:
            break

    return TableRenderer('Top Group Chats (2015)',
                         ['', 'Your<br/>messages', 'Total<br/>messages', '%'],
                         group_chat_ranking,
                         subtitle='By your messages sent')


def build_silent_group_chat_ranking_table(wxp):
    group_chat_ranking = []
    for thread in reversed(sorted(filter(lambda thread: len(_sent_chats_in_2015(thread)) == 0, wxp.group_threads), key=lambda thread: len(_chats_in_2015(thread)))):
        display_name = _group_chat_alias(thread.contact.display_name)
        if not display_name:
            continue
        my_sent = len(_sent_chats_in_2015(thread))
        total_sent = len(_chats_in_2015(thread))
        percent = round(100.0 * my_sent / total_sent, 1)
        group_chat_ranking.append((display_name, _int_with_comma(my_sent), _int_with_comma(total_sent), percent))
        if len(group_chat_ranking) == 8:
            break

    return TableRenderer('Peak Lurkage (2015)',
                         ['', 'Your<br/>messages', 'Total<br/>messages', '%'],
                         group_chat_ranking,
                         subtitle='Pleading the fifth')


def build_individual_chat_ranking_table(wxp):
    ranking = []
    for thread in list(reversed(sorted(wxp.individual_threads, key=lambda thread: len(_sent_chats_in_2015(thread)))))[:10]:
        display_name = thread.contact.display_name
        my_sent = len(_sent_chats_in_2015(thread))
        total = len(_chats_in_2015(thread))
        percent = round(100.0 * len(_sent_chats_in_2015(thread)) / total_sent_messages, 1)
        ranking.append((display_name, _int_with_comma(my_sent), percent, _int_with_comma(total)))
        if len(ranking) == 10:
            break

    top_five_percent = sum(x[2] for x in ranking[:5])

    return TableRenderer('2015 Top Contacts',
                         ['', 'Your<br/>messages', '% of all 2015<br/>sent messages', 'Total<br/>messages'],
                         ranking,
                         subtitle='%.1f%% of your sent messages were to just five people' % top_five_percent)


def _int_with_comma(integer):
    return '{:,d}'.format(integer)


if __name__ == '__main__':
    wxp = Parser('decrypted.db')
    userdata = UserData.initialize(wxp)

    def _chats_in_2015(thread):
        return filter(lambda message: message.timestamp >= beginning_of_2015 and message.timestamp < beginning_of_2016, thread.messages)

    def _sent_chats_in_2015(thread):
        return filter(lambda message: message.sent, _chats_in_2015(thread))

    def _chats_in_2016(thread):
        return filter(lambda message: message.timestamp >= beginning_of_2016 and message.timestamp < beginning_of_2017, thread.messages)

    def _sent_chats_in_2016(thread):
        return filter(lambda message: message.sent, _chats_in_2016(thread))

    total_individual_chats = sum([len(_chats_in_2015(thread)) for thread in wxp.individual_threads])
    individual_sent_messages = sum([len(_sent_chats_in_2015(thread)) for thread in wxp.individual_threads])
    group_sent_messages = sum([len(_sent_chats_in_2015(thread)) for thread in wxp.group_threads])
    total_sent_messages = individual_sent_messages + group_sent_messages

    # Figure out how many people we need
    # to categorize to get to 90% of chats
    cumulative = 0
    to_categorize = []
    for thread in list(reversed(sorted(wxp.individual_threads, key=lambda thread: len(_chats_in_2015(thread))))):
        cumulative += len(_chats_in_2015(thread))
        to_categorize.append(thread)
        if float(cumulative) / total_individual_chats > 0.90:
            break

    for thread in to_categorize:
        if getattr(thread, 'category', None):
            continue
        print thread.contact.display_name
        print
        categories_list = userdata.categories_as_list()
        for i in xrange(0, len(categories_list)):
            print '%4d - %s' % (i, categories_list[i].display_name)
        print

        user_entry = raw_input('Enter a number or name a new category: ').strip()
        if re.compile('\d+').match(user_entry):
            try:
                selected_category_index = int(user_entry)
                if selected_category_index >= 0 and selected_category_index < len(categories_list):
                    selected_category = categories_list[selected_category_index]
                    selected_category.add_thread(thread)
                    userdata.save()
                    continue
            except ValueError:
                pass

        if _slugify(user_entry) in userdata.categories.keys():
            # Matches an existing category by slug
            userdata.categories[_slugify(user_entry)].add_thread(thread)
            userdata.save()
            continue

        # Whole new category
        new_category = Category(user_entry)
        userdata.add_category(new_category)
        new_category.add_thread(thread)
        userdata.save()

    import codecs
    chart_file = codecs.open('chart.html', 'w', encoding='utf-8')
    chart_file.write(build_individual_chat_ranking_table(wxp).render())
    chart_file.close()
